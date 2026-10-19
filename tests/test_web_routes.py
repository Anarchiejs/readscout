"""Routes outside Python and Express (lot 5, 19 October 2026): Spring, NestJS and Go projects got an `undetermined`
receipt that described Python decorators, and the agent then did the work again with grep. Each framework below must be
listed deterministically, with its prefixes, whichever of extract=routes or extract=endpoints was asked.
"""
import pytest

from readscout import extract, tasks
from readscout.text import Line


def lines_of(path, text):
    return [Line(path, n, row) for n, row in enumerate(text.split('\n'), 1)]


def keys(res):
    return [f.key for f in res.facts]


SPRING = '''package shop;

import org.springframework.web.bind.annotation.*;

/**
 * Called before each @RequestMapping annotated method.
 */
@RestController
@RequestMapping("/owners/{ownerId}")
@PreAuthorize("hasRole('USER')")
public class PetController {

	@GetMapping("/pets/new")
	public String initCreationForm(Owner owner, ModelMap model) {
		return VIEW;
	}

	@PostMapping(value = "/pets/new")
	@Secured("ROLE_ADMIN")
	public String processCreationForm(@Valid Pet pet,
			BindingResult result) {
		return "redirect:/owners/{ownerId}";
	}

	@GetMapping({ "/pets", "/pets/" })
	public List<Pet> list() { return pets; }

	@RequestMapping(path = "/legacy", method = { RequestMethod.PUT, RequestMethod.PATCH })
	public void legacy() {}

	@DeleteMapping
	public void deleteAll() {}

	// @GetMapping("/commented")
	@GetMapping(BASE + "/computed")
	public void computed() {}
}
'''


def test_spring_handlers_with_class_prefix_methods_and_security():
    res = extract.run('routes', lines_of('PetController.java', SPRING))
    assert keys(res) == ['GET /owners/{ownerId}/pets/new initCreationForm', 'POST /owners/{ownerId}/pets/new processCreationForm',
                         'GET /owners/{ownerId}/pets list', 'GET /owners/{ownerId}/pets/ list',
                         'PUT,PATCH /owners/{ownerId}/legacy legacy', 'DELETE /owners/{ownerId} deleteAll']
    post = res.facts[1]
    assert (post.line, post.end) == (18, 20) and post.cite == '@PostMapping(value = "/pets/new")'
    assert '@Secured("ROLE_ADMIN")' in post.detail and "@PreAuthorize(\"hasRole('USER')\") (class)" in post.detail
    assert [(n, 'computed' in why) for _, n, why in res.unrecognized] == [(35, True)]      # the commented one is not read
    assert 'Spring handler methods' in res.scope and 'Python' not in res.scope


def test_kotlin_spring_handlers():
    src = '@RestController\n@RequestMapping("/api")\nclass Api {\n    @GetMapping("/items/{id}")\n    fun item(@PathVariable id: Long): Item = repo.find(id)\n}'
    assert keys(extract.run('endpoints', lines_of('Api.kt', src))) == ['GET /api/items/{id} item']


NEST = '''import { Controller, Get, Post, Delete, UseGuards } from '@nestjs/common';

@ApiTags('articles')
@Controller('articles')
@UseGuards(AuthGuard)
export class ArticleController {
  constructor(private readonly service: ArticleService) {}

  @ApiOperation({ summary: 'Get all articles' })
  @Get()
  async findAll(@Query() query: any): Promise<IArticlesRO> {
    return this.service.findAll(query);
  }

  @Get(':slug/comments')
  findComments(@Param('slug') slug: string) { return []; }

  @UseGuards(AdminGuard)
  @Delete(':slug')
  async delete(@Param() params) {}
}
'''


def test_nest_handlers_with_controller_prefix_and_guards():
    res = extract.run('routes', lines_of('article.controller.ts', NEST))
    assert keys(res) == ['GET /articles findAll', 'GET /articles/:slug/comments findComments', 'DELETE /articles/:slug delete']
    assert res.facts[0].line == 10 and res.facts[0].end == 11
    assert '@UseGuards(AdminGuard)' in res.facts[2].detail and '@UseGuards(AuthGuard) (class)' in res.facts[2].detail
    assert not res.unrecognized


def test_a_nest_global_prefix_is_stated():
    lines = lines_of('article.controller.ts', NEST) + lines_of('main.ts', "const app = await NestFactory.create(AppModule);\napp.setGlobalPrefix('api');")
    res = extract.run('endpoints', lines)
    assert any('Global prefix "api" set at main.ts:2' in c for c in res.coverage)


def test_angular_or_plain_typescript_decorators_are_not_routes():
    src = "import { Component } from '@angular/core';\n@Component({ selector: 'x' })\nexport class X { @Input() get: string; }"
    assert extract.run('routes', lines_of('x.component.ts', src)).facts == []


GO_MAIN = '''package main

func main() {
	r := gin.Default()
	v1 := r.Group("/api")
	users.UsersRegister(v1.Group("/users"))
	v1.Use(users.AuthMiddleware(true))
	users.ProfileRegister(v1.Group("/profiles"))
	r.GET("/ping", func(c *gin.Context) {
		c.JSON(200, gin.H{"message": "pong"})
	})
}
'''
GO_USERS = '''package users

func UsersRegister(router *gin.RouterGroup) {
	router.POST("", UsersRegistration)
	router.POST("/login", UsersLogin)
}

func ProfileRegister(router *gin.RouterGroup) {
	router.DELETE("/:username/follow", auth.Required(), ProfileUnfollow)
}

func FetchProfile(c *gin.Context) {
	resp, _ := http.Get("https://example.com/x")
	c.JSON(http.StatusOK, gin.H{"profile": resp})
}
'''


def test_go_group_prefixes_flow_through_registration_functions():
    res = extract.run('routes', lines_of('hello.go', GO_MAIN) + lines_of('users/routers.go', GO_USERS))
    assert sorted(keys(res)) == sorted(['POST /api/users UsersRegistration', 'POST /api/users/login UsersLogin',
                                        'DELETE /api/profiles/:username/follow ProfileUnfollow', 'GET /ping inline func'])
    follow = next(f for f in res.facts if 'follow' in f.key)
    assert 'middlewares: auth.Required()' in follow.detail and not res.unrecognized
    assert 'x.Use(...) are not attributed' in res.scope


def test_go_registrations_without_their_caller_are_listed_with_a_note():
    res = extract.run('endpoints', lines_of('users/routers.go', GO_USERS))
    assert keys(res) == ['POST "" UsersRegistration', 'POST /login UsersLogin', 'DELETE /:username/follow ProfileUnfollow']
    assert any('UsersRegister(router)' in c and 'not applied' in c for c in res.coverage)


def test_chi_and_gorilla_registrations():
    src = ('func routes(r chi.Router) {\n\tr.Get("/health", health)\n\tr.Route("/v2", func(sub chi.Router) {})\n}\n'
           'func mux() {\n\tm := mux.NewRouter()\n\tapi := m.PathPrefix("/api")\n\tapi.HandleFunc("/items", items).Methods("GET", "POST")\n}')
    assert set(keys(extract.run('routes', lines_of('r.go', src)))) == {'GET /health health', 'GET,POST /api/items items'}


def test_the_protection_filter_applies_to_every_framework():
    lines = lines_of('PetController.java', SPRING) + lines_of('article.controller.ts', NEST) + lines_of('users/routers.go', GO_USERS)
    res = extract.run('endpoints!Secured,AdminGuard,auth.Required', lines)
    found = keys(res)
    assert 'POST /owners/{ownerId}/pets/new processCreationForm' not in found and 'DELETE /articles/:slug delete' not in found
    assert 'DELETE /:username/follow ProfileUnfollow' not in found
    assert 'GET /articles findAll' in found and 'POST /login UsersLogin' in found
    assert res.excerpts         # the filtered list brings the source lines a check reads


def test_routes_and_endpoints_read_the_same_frameworks():
    lines = lines_of('PetController.java', SPRING) + lines_of('app.py', '@app.get("/x")\ndef x(): ...') + lines_of('server.js', "app.get('/y', h)")
    a, b = extract.run('routes', lines), extract.run('endpoints', lines)
    assert keys(a) == keys(b) and {'GET /x x', 'GET /y'} <= set(keys(a))


def test_an_unsupported_language_still_says_what_is_covered(tmp_path, monkeypatch):
    (tmp_path / 'routes.rb').write_text("get '/users', to: 'users#index'\n")
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    text = tasks.ask(['routes.rb'], 'list routes', extraction='routes')
    assert 'status: undetermined' in text and 'Spring' in text and 'Go router' in text and 'Python endpoint' in text


@pytest.mark.parametrize('kind', ['routes', 'endpoints'])
def test_spring_receipt_is_complete(tmp_path, monkeypatch, kind):
    (tmp_path / 'PetController.java').write_text(SPRING.replace('	@GetMapping(BASE + "/computed")\n	public void computed() {}\n', ''))
    monkeypatch.setattr(tasks, 'load_config', lambda: ({'models': {}}, [tmp_path]))
    monkeypatch.setattr(tasks, 'record', lambda entry: None)
    text = tasks.ask(['PetController.java'], 'list the handlers', extraction=kind)
    assert 'status: complete' in text and 'PetController.java:13-14 | GET /owners/{ownerId}/pets/new initCreationForm' in text
