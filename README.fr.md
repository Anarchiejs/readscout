# readscout (français)

**Des modèles locaux lisent tes fichiers pour ton agent de code.** Quand Claude Code ou Codex a besoin d'informations
dans de gros fichiers, un long journal ou un dossier entier, il demande à readscout au lieu de tout lire lui-même. Un
petit modèle sur ta propre carte graphique lit les fichiers et répond en quelques lignes, et **chaque affirmation est
accompagnée d'une citation que readscout a vérifiée mot pour mot dans la source**, avec son vrai `fichier:ligne`.
Ton agent garde sa fenêtre de contexte (et ton quota) pour le vrai raisonnement. Rien ne quitte ta machine.

[English version](README.md)

## Ce que ça fait

readscout est un serveur [MCP](https://modelcontextprotocol.io) avec trois outils, plus un skill qui indique à ton
agent quand s'en servir :

| Outil | Ton agent lui donne | Il reçoit |
|---|---|---|
| `local_ask(paths, question)` | des fichiers ou dossiers (1,5 Mo au plus) et une question | quelques constats, chacun avec une citation vérifiée et son vrai `fichier:ligne` |
| `local_digest(path)` | un long journal ou une sortie de commande | la cause racine et les erreurs distinctes, citations vérifiées |
| `local_edit(paths, instruction, gate)` | des fichiers, un changement précis, des commandes de contrôle (tes tests) | `APPLIED` + le diff si tes contrôles passent, sinon `ESCALATE` et les fichiers restaurés à l'identique |

Un constat dont la citation est introuvable dans la source est supprimé ; les numéros de ligne sont calculés par
readscout, jamais par le modèle ; les questions à négation (« sans », « pas », « manque ») passent automatiquement au
gros modèle ; une modification n'est gardée que si tes tests passent. Les modèles libèrent la RAM et la VRAM tout
seuls : Ollama les décharge une minute après le dernier appel, et readscout dès que la session de l'agent se termine
(`readscout stop` libère tout immédiatement).

## Prérequis

- Windows, macOS ou Linux ; [Claude Code](https://claude.com/claude-code) et/ou [Codex](https://developers.openai.com/codex).
- [Ollama](https://ollama.com) pour faire tourner les modèles (l'installeur peut l'installer).
- Une carte graphique de 6 Go ou plus est conseillée (NVIDIA, AMD ou Apple silicon) et 16 Go de RAM ; 8 Go de VRAM et
  32 Go de RAM donnent la meilleure configuration mesurée. Fonctionne aussi sans carte graphique, lentement.
- 7 à 25 Go d'espace disque pour les modèles.

## Installation

Choisis une option. **A** configure tout pour Claude Code et Codex. **B** est le plus rapide si tu n'utilises que
Claude Code. **C** fait la même chose que A, à la main.

### Option A : installeur en une ligne (conseillé)

Windows (PowerShell) :
```powershell
irm https://raw.githubusercontent.com/Anarchiejs/readscout/main/install.ps1 | iex
```
macOS / Linux :
```sh
curl -fsSL https://raw.githubusercontent.com/Anarchiejs/readscout/main/install.sh | sh
```

L'installeur demande avant d'installer quoi que ce soit : **uv** (gestionnaire Python d'Astral, qui apporte son
propre Python), **Ollama** s'il manque, puis **readscout**. Il ouvre ensuite la **page de configuration** dans ton
navigateur (`http://127.0.0.1:8765/setup`) :
- **Ta machine** : mémoire du GPU et RAM détectées et pré-remplies, curseurs ajustables (VRAM 6-24 Go, RAM 16-64 Go) ;
- **Modèles** : ceux conseillés pour ta machine, chacun avec un bouton **Install** (un clic, barre de progression),
  puis **Use these models** ;
- **Agents** : **Connect** pour Claude Code et/ou Codex (serveur MCP + skill) ;
- **Dossiers de projets** : ajoute les dossiers que les modèles locaux ont le droit de lire ;
- **Vérification** : tout doit être vert.

Redémarre Claude Code / Codex.

### Option B : plugin Claude Code

Uniquement pour Claude Code. Installe d'abord [uv](https://docs.astral.sh/uv/getting-started/installation/) et
[Ollama](https://ollama.com). Dans Claude Code :

```text
/plugin marketplace add Anarchiejs/readscout
/plugin install readscout@readscout
```

Le plugin apporte le skill et le serveur MCP (lancé par `uvx`, rien d'autre à installer). Ensuite, dans un terminal,
pour télécharger les modèles et autoriser un dossier :

```sh
uvx --from https://github.com/Anarchiejs/readscout/releases/download/v0.1.2/readscout-0.1.2-py3-none-any.whl readscout setup
```

C'est la même page que pour l'option A : installe les modèles et ajoute tes dossiers (la partie « Agents » est déjà
faite par le plugin). Redémarre Claude Code.

### Option C : installation manuelle

```sh
# 1. Ollama : https://ollama.com/download (vérifie qu'il tourne)
# 2. uv :     https://docs.astral.sh/uv/getting-started/installation/
# 3. readscout
uv tool install https://github.com/Anarchiejs/readscout/releases/download/v0.1.2/readscout-0.1.2-py3-none-any.whl
# 4. modèles conseillés pour ta machine
readscout pull
# 5. connecter tes agents
readscout install-agent claude
readscout install-agent codex
# 6. autoriser un dossier de projet (à répéter pour chaque projet)
readscout register mon-app /chemin/vers/mon-app
# 7. vérifier
readscout doctor
```

Redémarre Claude Code / Codex.

## Premiers pas

1. `readscout doctor` doit finir par `All good.`
2. Ouvre un projet autorisé dans Claude Code ou Codex.
3. Pose une question qui demande beaucoup de lecture, avec tes mots, par exemple :
   - « Quelles routes de `src/routes` ne vérifient pas l'authentification ? »
   - « Où est gérée l'expiration des sessions dans ce dépôt ? »
   - « Résume ce que fait le dossier `lib/`. »
   - « Lance les tests et dis-moi pourquoi ils échouent » (l'agent enregistre la sortie dans un fichier et la digère).
4. Tu vois l'agent appeler `local_ask` ou `local_digest` et recevoir un reçu court au lieu d'ouvrir chaque fichier.
   Le premier appel charge le modèle en mémoire (10 à 30 s), les suivants sont plus rapides.
5. Ce que ça t'a fait économiser : `readscout stats`, ou `readscout dashboard` pour la page de suivi.

Tu peux aussi appeler les outils depuis un terminal pour voir ce qu'ils renvoient :
`readscout ask src -q "Quelles fonctions lisent des variables d'environnement ?"` ou `readscout digest build.log`.

## Au quotidien

Tu travailles comme d'habitude : le skill indique à l'agent quand déléguer. Il utilise readscout pour les faits
dispersés dans des fichiers qu'il n'a pas lus, comprendre un dossier sans le lire, les longs journaux et sorties de
tests, et les petits changements mécaniques entièrement décrits (docstrings, annotations de type, renommage, squelette
de tests), toujours contrôlés par tes tests. Il garde pour lui ce qu'un `grep` donne, les fichiers courts, et tout
**jugement** (revue de code, « y a-t-il un bug », architecture, faits du monde réel).

## Dépannage

| Symptôme | Solution |
|---|---|
| Quelque chose ne va pas | `readscout doctor` liste ce qui manque, avec la commande qui le corrige |
| « Ollama is not installed » | installe ou démarre Ollama (sous Windows et macOS, readscout le lance tout seul) |
| « Model ... is not installed yet » | `readscout pull` |
| « File not found inside a registered project » | `readscout register <id> <dossier du projet>` |
| L'agent n'utilise jamais readscout | redémarre l'agent après l'installation ; `readscout doctor` vérifie la connexion |
| Réponses lentes | normal pour le gros modèle sur une petite carte (20 à 60 s) ; le petit répond en quelques secondes |

## Sécurité, limites, désinstallation

- Les modèles tournent uniquement sur `127.0.0.1` ; les modèles cloud d'Ollama sont refusés (par leur nom et quand Ollama
  les signale comme servis à distance), jamais de modèle en ligne. Le modèle n'a aucun outil ; seul
  readscout lit les fichiers, et seulement dans les dossiers autorisés. `.env*`, `.git`, clés, fichiers d'identifiants et
  binaires sont refusés (majuscules comprises) ; les secrets courants sont masqués (par motifs : aucun masque n'est
  parfait, garde les vrais identifiants hors des dossiers autorisés), et `local_edit` refuse les fichiers qui en
  contiennent. `local_edit` écrit de façon atomique, n'écrase jamais un fichier modifié pendant l'attente du modèle, et
  ne restaure que ce qu'il a écrit ; ses commandes `gate` s'exécutent avec tes droits, choisies par l'agent.
  Sont stockés en local : `config.json` et `metrics.jsonl` (outil, modèle, tailles, durées ; jamais de contenu).
  Détails : [SECURITY.md](SECURITY.md).
- Une citation vérifiée prouve que la ligne existe, pas que le modèle l'a bien comprise. Ne délègue ni revue de code,
  ni recherche de bugs, ni vérification de faits.
- Désinstaller : `readscout uninstall-agent claude` (ou `/plugin uninstall readscout@readscout`),
  `readscout uninstall-agent codex`, puis `uv tool uninstall readscout`. Les modèles restent dans Ollama (`ollama rm`).

Commandes, modèles et résultats détaillés : [README.md](README.md) et [docs/BENCHMARK.md](docs/BENCHMARK.md).

## Licence

[MIT](LICENSE)
