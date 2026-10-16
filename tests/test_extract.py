"""Deterministic extractors, tested on code shapes that are not the benchmark's repositories."""
from readscout import extract, tasks
from readscout.text import Line


def files(**named):
    out = []
    for name, text in named.items():
        out += [Line(name.replace('__', '/').replace('_py', '.py').replace('_ts', '.ts').replace('_js', '.js'), i, t)
                for i, t in enumerate(text.split('\n'), 1)]
    return out


def keys(res):
    return sorted(g[0].key for g in res.groups())


# ---------------------------------------------------------------- environment variables

def test_env_direct_bracket_destructured_alias_and_python_forms():
    lines = files(a_ts='''const url = process.env.DATABASE_URL;
const k = process.env["API_KEY"];
const { PORT, HOST: host, MODE = "dev" } = process.env;
const env = process.env;
const t = env.TOKEN_X + env["OTHER"];
// process.env.IN_A_COMMENT
const v = import.meta.env.VITE_FLAG;''', b_py='''import os
from os import getenv
a = os.environ["PY_A"]
b = os.environ.get("PY_B", "x")
c = os.getenv("PY_C")
d = getenv("PY_D")
# os.environ["COMMENTED"]''')
    res = extract.run('env', lines)
    assert keys(res) == ['API_KEY', 'DATABASE_URL', 'HOST', 'MODE', 'OTHER', 'PORT', 'PY_A', 'PY_B', 'PY_C', 'PY_D', 'TOKEN_X', 'VITE_FLAG']
    assert not res.unrecognized


def test_env_deduplicates_by_name_and_keeps_every_position():
    lines = files(a_js='x = process.env.A\ny = process.env.A\nz = process.env.B')
    groups = {g[0].key: g for g in extract.run('env', lines).groups()}
    assert [f.line for f in groups['A']] == [1, 2] and len(groups['B']) == 1
    assert groups['A'][0].cite == 'x = process.env.A'


def test_env_computed_names_are_reported_not_guessed():
    res = extract.run('env', files(a_js='const v = process.env[name];', b_py='import os\nv = os.environ[key]\nw = os.getenv(other)'))
    assert keys(res) == [] and len(res.unrecognized) == 3


# ---------------------------------------------------------------- Express routes

def test_express_direct_chained_and_multiline_routes_with_middlewares():
    lines = files(r_js='''router.get('/users', auth, admin, listUsers);
app.post("/login", login);
router.route('/items/:id')
  .get(auth, getItem)
  .put(auth, validate, updateItem)
  .delete(removeItem);
app.get('/health',
  (req, res) => res.send('ok'));
axios.get('/api/users', { headers });
cache.get('/key');''')
    res = extract.run('routes', lines)
    assert keys(res) == ['DELETE /items/:id', 'GET /health', 'GET /items/:id', 'GET /users', 'POST /login', 'PUT /items/:id']
    by = {g[0].key: g[0] for g in res.groups()}
    assert 'middlewares: auth, admin | handler: listUsers' in by['GET /users'].detail
    assert 'middlewares: auth, validate | handler: updateItem' in by['PUT /items/:id'].detail
    assert 'middlewares: none | handler: removeItem' in by['DELETE /items/:id'].detail
    assert by['GET /users'].line == 1 and by['GET /health'].end == 8


def test_express_computed_path_is_reported():
    res = extract.run('routes', files(r_js='router.get(PATH, handler);\napp.post(`/x/${id}`, h);'))
    assert keys(res) == [] and len(res.unrecognized) == 2


# ---------------------------------------------------------------- Python endpoints

PY = '''from fastapi import APIRouter, Depends, FastAPI
router = APIRouter(dependencies=[Depends(get_current_user)])
public = APIRouter()
app = FastAPI()
app.include_router(admin, dependencies=[Depends(require_admin)])

@router.get("/items")
async def items(q: str = None): ...

@public.post("/signup", dependencies=[Depends(rate_limit)])
def signup(body: Body, user: CurrentUser): ...

@public.get("/status")
def status(): ...

@public.get(PATH)
def computed(): ...
'''


def test_endpoints_keep_decorator_signature_and_router_dependencies():
    res = extract.run('endpoints', files(api_py=PY))
    by = {g[0].key: g[0] for g in res.groups()}
    assert sorted(by) == ['GET /items items', 'GET /status status', 'POST /signup signup']
    assert 'router dependencies: [Depends(get_current_user)]' in by['GET /items items'].detail
    assert 'decorator dependencies: [Depends(rate_limit)]' in by['POST /signup signup'].detail
    assert by['GET /items items'].line == 7 and by['GET /items items'].cite == '@router.get("/items")'
    assert len(res.unrecognized) == 1 and 'computed path' in res.unrecognized[0][2]


def test_endpoints_lacking_a_dependency_name_the_scope_and_use_router_dependencies():
    res = extract.run('endpoints!CurrentUser', files(api_py=PY))
    assert sorted(g[0].key for g in res.groups()) == ['GET /items items', 'GET /status status']   # signup has CurrentUser
    assert 'not a guarantee about the whole application' in res.scope
    res = extract.run('endpoints!get_current_user', files(api_py=PY))
    assert 'GET /items items' not in keys(res)       # the router dependency counts


def test_endpoints_unlinkable_include_router_and_syntax_errors_are_reported():
    res = extract.run('endpoints', files(a_py='app.include_router(users.router, dependencies=[Depends(x)])', b_py='def broken(:'))
    reasons = ' '.join(r[2] for r in res.unrecognized)
    assert 'cannot be linked' in reasons and 'does not parse' in reasons


# ---------------------------------------------------------------- Supabase

def test_supabase_chains_across_lines_and_ignores_array_from():
    lines = files(db_ts='''const a = await supabase.from('users').select('*').eq('id', 1);
const b = await supabase
  .from("orders")
  .upsert([row])
  .select();
const c = Array.from('abc').map(x => x);
const d = supabase.from(tableName).select();
const e = await supabase.rpc('do_thing', { a: 1 });''')
    res = extract.run('supabase', lines)
    assert keys(res) == ['orders.select', 'orders.upsert', 'rpc.do_thing', 'users.select']
    assert len(res.unrecognized) == 1 and 'computed table' in res.unrecognized[0][2]
    by = {g[0].key: g[0] for g in res.groups()}
    assert by['orders.upsert'].line == 3 and by['orders.upsert'].end == 4


# ---------------------------------------------------------------- receipt

def test_extract_receipt_status_is_structural(tmp_path, monkeypatch):
    clean = tasks.extract_receipt(extract.run('env', files(a_js='x = process.env.A')), 100, 40, 'local_ask extract=env')
    assert 'status: complete' in clean and '« x = process.env.A »' in clean and 'no model' in clean
    partial = tasks.extract_receipt(extract.run('env', files(a_js='x = process.env[n]')), 100, 40, 'local_ask extract=env')
    assert 'status: partial' in partial and 'Not recognized (1)' in partial and 'a.js:1' in partial


def test_unknown_extraction_is_a_clear_error():
    try:
        extract.run('nonsense', [])
    except ValueError as e:
        assert 'env, routes, endpoints, supabase' in str(e)
    else:
        raise AssertionError('expected ValueError')


def test_comment_lines_do_not_shift_the_reported_line():
    lines = files(a_js='// a long comment line that is blanked before scanning\n/* another one */\nconst x = process.env.LATE;\n  // trailing comment\nconst y = process.env.LAST;')
    by = {g[0].key: g[0] for g in extract.run('env', lines).groups()}
    assert (by['LATE'].line, by['LATE'].cite) == (3, 'const x = process.env.LATE;')
    assert (by['LAST'].line, by['LAST'].cite) == (5, 'const y = process.env.LAST;')


# ---------------------------------------------------------------- the three defects found by campaign 2

JOI = '''const envVarsSchema = Joi.object()
  .keys({
    NODE_ENV: Joi.string().valid('production', 'test').required(),
    PORT: Joi.number().default(3000),
    JWT_RESET_PASSWORD_EXPIRATION_MINUTES: Joi.number()
      .default(10),
    nested: Joi.object({ INNER_UPPER: Joi.string() }),
    SMTP_HOST: Joi.string().description('server'),
  })
  .unknown();
const schema = z.object({ API_URL: z.string().url(), debug: z.boolean() });'''


def test_env_lists_variables_declared_in_joi_and_zod_schemas_even_when_never_read_by_name():
    res = extract.run('env', files(config_js=JOI))
    assert keys(res) == ['API_URL', 'JWT_RESET_PASSWORD_EXPIRATION_MINUTES', 'NODE_ENV', 'PORT', 'SMTP_HOST']    # top level only, no nested INNER_UPPER
    by = {g[0].key: g[0] for g in res.groups()}
    assert by['PORT'].line == 4 and by['PORT'].detail == 'declared in a validation schema'


def test_env_lists_pydantic_settings_fields():
    res = extract.run('env', files(s_py='from pydantic_settings import BaseSettings\nclass Settings(BaseSettings):\n    database_url: str\n    _private: int = 1\n    debug: bool = False'))
    assert keys(res) == ['DATABASE_URL', 'DEBUG']


def test_a_secret_looking_name_does_not_break_the_code_the_schema_is_read_from(tmp_path):
    # redaction used to swallow `JWT_SECRET: Joi.string().required().description(` and the closing bracket, losing every later key
    (tmp_path / 'config.js').write_text("const s = Joi.object().keys({\n  A_ONE: Joi.string(),\n  JWT_SECRET: Joi.string().required().description('JWT secret key'),\n  B_TWO: Joi.number(),\n});\n")
    from readscout.text import load_lines
    res = extract.run('env', load_lines('config.js', [tmp_path]))
    assert keys(res) == ['A_ONE', 'B_TWO', 'JWT_SECRET']


def test_redaction_no_longer_breaks_python_files_so_their_endpoints_are_found(tmp_path):
    (tmp_path / 'login.py').write_text('from fastapi import APIRouter\nrouter = APIRouter()\n\n@router.post("/login")\ndef login(form_data):\n    return authenticate(email=form_data.username, password=form_data.password)\n')
    from readscout.text import load_lines
    res = extract.run('endpoints', load_lines('login.py', [tmp_path]))
    assert keys(res) == ['POST /login login'] and not res.unrecognized


def test_chained_route_methods_are_reported_on_their_own_line():
    res = extract.run('routes', files(r_js="router.route('/x')\n  .get(a)\n  .post(b);"))
    assert {g[0].key: g[0].line for g in res.groups()} == {'GET /x': 2, 'POST /x': 3}


def test_endpoints_lacking_several_names_and_the_scope_says_it_is_not_public():
    code = files(api_py='''from fastapi import APIRouter, Depends
router = APIRouter()

@router.get("/me")
def me(user: CurrentUser): ...

@router.get("/admin", dependencies=[Depends(get_current_active_superuser)])
def admin(): ...

@router.get("/open")
def open_(): ...''')
    one = extract.run('endpoints!CurrentUser', code)
    both = extract.run('endpoints!CurrentUser,get_current_active_superuser', code)
    assert keys(one) == ['GET /admin admin', 'GET /open open_'] and keys(both) == ['GET /open open_']
    assert 'not the same as "public"' in both.scope and both.inspected == 3


def test_empty_results_are_undetermined_not_complete():
    empty = extract.run('env', files(a_js='const x = 1;'))
    text = tasks.extract_receipt(empty, 10, 40, 'q')
    assert 'status: undetermined' in text and empty.status == 'undetermined' and 'does not prove it is absent' in text
    filtered = extract.run('endpoints!Dep', files(a_py='@router.get("/x")\ndef f(d: Dep): ...'))
    text = tasks.extract_receipt(filtered, 10, 40, 'q')
    assert 'status: complete' in text and 'None of the 1 item(s) inspected matches the filter' in text
