# readscout (français)

**Des modèles locaux lisent tes fichiers pour ton agent de code.** Quand Claude Code ou Codex a besoin d'informations
dans de gros fichiers, un long journal ou un dossier entier, il demande à readscout au lieu de tout lire lui-même. Un
petit modèle sur ta propre carte graphique lit les fichiers et répond en quelques lignes, et **chaque affirmation est
accompagnée d'une citation que readscout a vérifiée mot pour mot dans la source**, avec son vrai `fichier:ligne`.
La citation et la ligne sont prouvées ; la phrase qui les accompagne reste la lecture du modèle, donc ton agent ouvre
les lignes citées avant toute décision.
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
seuls, quel que soit le moteur (Ollama, ou le `llama-server` de llama.cpp que readscout lance et arrête lui-même) : une
minute après le dernier appel, et dès que la session de l'agent se termine (`readscout stop` libère tout immédiatement).

## Prérequis

- Windows, macOS ou Linux ; [Claude Code](https://claude.com/claude-code) et/ou [Codex](https://developers.openai.com/codex).
- [Ollama](https://ollama.com) pour faire tourner les modèles (l'installeur peut l'installer).
- Une carte graphique de 6 Go ou plus est conseillée (NVIDIA, AMD ou Apple silicon) et 16 Go de RAM ; 8 Go de VRAM et
  32 Go de RAM donnent la meilleure configuration mesurée. Fonctionne aussi sans carte graphique, lentement.
- 7 à 25 Go d'espace disque pour les modèles.
- Facultatif, seulement pour lire plus vite les gros volumes avec le modèle 26B : [llama.cpp](https://github.com/ggml-org/llama.cpp)
  (`llama-server`, que l'installeur n'installe pas ; voir [Plus rapide avec llama.cpp](#plus-rapide-avec-llamacpp-facultatif)).
  Il réutilise les fichiers de modèle qu'Ollama a déjà téléchargés. Avec un GPU **NVIDIA**, prends un build **CUDA**
  (environ 150 Mo, plus environ 400 Mo de runtime CUDA sous Windows) : les builds CUDA 13 demandent un pilote NVIDIA 580 ou
  plus récent (`nvidia-smi` affiche le tien), prends un build CUDA 12 pour un pilote plus ancien
  ([table de compatibilité NVIDIA](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)).
  Le build Vulkan qu'installe `winget install llama.cpp` était plus lent qu'Ollama sur une carte NVIDIA. AMD (build ROCm
  ou Vulkan) et Apple silicon (build Metal) n'ont pas été mesurés : compare avec `readscout bench`.

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
pour télécharger les modèles :

```sh
uvx --from https://github.com/Anarchiejs/readscout/releases/download/v0.1.6/readscout-0.1.6-py3-none-any.whl readscout setup
```

C'est la même page que pour l'option A : installe les modèles (la partie « Agents » est déjà faite par le
plugin). Redémarre Claude Code.

### Option C : installation manuelle

```sh
# 1. Ollama : https://ollama.com/download (vérifie qu'il tourne)
# 2. uv :     https://docs.astral.sh/uv/getting-started/installation/
# 3. readscout
uv tool install https://github.com/Anarchiejs/readscout/releases/download/v0.1.6/readscout-0.1.6-py3-none-any.whl
# 4. modèles conseillés pour ta machine
readscout pull
# 5. connecter tes agents
readscout install-agent claude
readscout install-agent codex
# 6. vérifier
readscout doctor
```

Redémarre Claude Code / Codex.

## Premiers pas

1. `readscout doctor` doit finir par `All good.`
2. Ouvre un projet dans Claude Code ou Codex.
3. Pose une question qui demande beaucoup de lecture, avec tes mots, par exemple :
   - « Quelles routes de `src/routes` ne vérifient pas l'authentification ? »
   - « Où est gérée l'expiration des sessions dans ce dépôt ? »
   - « Résume ce que fait le dossier `lib/`. »
   - « Lance les tests et dis-moi pourquoi ils échouent » (l'agent enregistre la sortie dans un fichier et la digère).
4. Tu vois l'agent appeler `local_ask` ou `local_digest` et recevoir un reçu court au lieu d'ouvrir chaque fichier.
   Le premier appel charge le modèle en mémoire (10 à 30 s), les suivants sont plus rapides.
5. Consulte les lectures locales : `readscout stats`, ou `readscout dashboard` pour la page de suivi.
   La réduction de texte exprimée en tokens est une estimation, pas une économie mesurée chez l'agent.

Tu peux aussi appeler les outils depuis un terminal pour voir ce qu'ils renvoient :
`readscout ask src -q "Quelles fonctions lisent des variables d'environnement ?"` ou `readscout digest build.log`.

## Au quotidien

Tu travailles comme d'habitude : le skill indique à l'agent quand déléguer. Il utilise readscout pour les faits
dispersés dans des fichiers qu'il n'a pas lus, comprendre un dossier sans le lire, les longs journaux et sorties de
tests, et les petits changements mécaniques entièrement décrits (docstrings, annotations de type, renommage, squelette
de tests), toujours contrôlés par tes tests. Il garde pour lui ce qu'un `grep` donne, les fichiers courts, et tout
**jugement** (revue de code, « y a-t-il un bug », architecture, faits du monde réel).

## Plus rapide avec llama.cpp (facultatif)

Ollama est le moteur par défaut et reste le meilleur choix sur la plupart des machines. [llama.cpp](https://github.com/ggml-org/llama.cpp)
lit les gros prompts environ deux fois plus vite avec un modèle de qualité à mélange d'experts, mais écrit plus
lentement. Mesuré sur RTX 4060 Ti 8 Go + 32 Go de RAM (Ollama 0.40.3, llama.cpp b11636 CUDA, mêmes fichiers GGUF, Gemma 4,
[résultats complets](docs/bench-results/rtx4060ti-8gb_32gb-ram_windows_ollama-vs-llamacpp.json)) :

| | Ollama | llama.cpp (CUDA) |
|---|---|---|
| `gemma4:26b`, lecture du prompt | 554 à 566 tokens/s | 1 008 à 1 205 tokens/s (`--n-cpu-moe 30`) |
| `gemma4:26b`, écriture | 42 à 45 tokens/s | 24 à 25 tokens/s |
| `gemma4:26b`, dossier de 181 Ko, fichiers nouveaux (3 morceaux d'environ 25k tokens) | 181 s | 127 s |
| `gemma4:26b`, le même dossier redemandé (prompt en cache) | 30 s | 54 s |
| `gemma4:26b`, bench public (petites entrées) | 0,93, 23 s/tâche, modifs 9,7 s | 0,94, 23 s/tâche, modifs 14 s |
| `gemma4:12b`, bench public | 0,94, 24 s/tâche, modifs 6/7 en 12 s | 0,93, 50 s/tâche (2 fois plus lent), modifs 6,8/7 en 25 s |
| `gemma4:e4b`, bench public | 0,83, 5,8 s/tâche, modifs 7/7 | 0,86, 16,9 s/tâche (3 fois plus lent), modifs 6,8/7 |

Donc llama.cpp ne rapporte qu'une chose : lire des entrées **nouvelles** et grosses avec le 26B (ici 1,4 fois plus vite
au total, 2 fois sur le prompt seul). Il perd quand on repose une question sur les mêmes fichiers (Ollama garde le début
du prompt en cache et écrit plus vite), et il est plus lent pour le modèle rapide et le 12B. C'est pourquoi chaque modèle
peut tourner sur son propre moteur. Le build Vulkan qu'installe `winget install llama.cpp` était plus lent qu'Ollama sur
une carte NVIDIA : avec NVIDIA, prends le build CUDA sur la
[page des versions](https://github.com/ggml-org/llama.cpp/releases) (`llama-bXXXX-bin-win-cuda-13.x-x64.zip` et le
`cudart-...zip` correspondant ; voir [Prérequis](#prérequis) pour le pilote). Si ta machine a aussi un GPU intégré, ajoute
`--args "--device CUDA0"` (ou `Vulkan0`) pour que le modèle ne soit pas réparti dessus ; `readscout doctor` affiche les
identifiants des périphériques.

```sh
readscout engine llamacpp --quality ollama:gemma4:26b --binary chemin/vers/llama-server --args "--n-cpu-moe 30"
readscout engine                                         # fast : ollama gemma4:e4b, quality : llamacpp ...
readscout doctor
readscout bench --models gemma4:26b,llamacpp:quality     # compare les deux moteurs sur ta machine
```

Seuls les modèles que tu nommes passent à llama.cpp : ci-dessus, le modèle rapide reste sur Ollama
(`--fast ollama:gemma4:e4b` le passerait aussi, `--quality ollama` remet le modèle de qualité sur Ollama).
`ollama:<modèle>` réutilise le fichier qu'Ollama a déjà téléchargé (rien à retélécharger) ; un chemin `.gguf` marche
aussi. readscout lance alors `llama-server` lui-même sur un port local libre (flash attention, cache KV 8 bits,
micro-lot de 2048, pénalité de répétition d'Ollama), garde un seul modèle chargé, partagé par toutes tes sessions, et
l'arrête après le même délai d'inactivité qu'Ollama (une minute) ou à la fin de la session ; `readscout stop` l'arrête
tout de suite. Sur une carte de 8 Go, les deux moteurs ne peuvent pas garder chacun un modèle, donc ils se relaient :
avant que llama.cpp charge un modèle, readscout décharge ceux d'Ollama, et avant un appel à Ollama il arrête son
llama-server inactif (jamais au milieu d'une requête d'une autre session ; changer coûte un chargement de modèle,
quelques secondes depuis la RAM). Des options en plus passent par `--args` pour tous les modèles, ou dans `config.json` sous
`llamacpp.models.<tier>.args` pour un seul (le 26B ci-dessus utilisait `["--n-cpu-moe", "30"]`). Tu as déjà ton propre
`llama-server` ? Donne son adresse : `--fast http://127.0.0.1:8080` (readscout ne le lancera ni ne l'arrêtera jamais).
Tous les modèles sur Ollama : `readscout engine ollama` (tes modèles llama.cpp sont gardés : `readscout engine llamacpp`
les remet). Redémarre ton agent après chaque changement.

## Dépannage

| Symptôme | Solution |
|---|---|
| Quelque chose ne va pas | `readscout doctor` liste ce qui manque, avec la commande qui le corrige |
| « Ollama is not installed » | installe ou démarre Ollama (sous Windows et macOS, readscout le lance tout seul) |
| « Model ... is not installed yet » | `readscout pull` |
| Un modèle refuse de charger (« out of memory » ou « Gemma4Assistant requires ctx_other ») alors que le GPU semble libre | un `llama-server.exe` du dossier d'Ollama (`...\Ollama\lib\ollama`) est resté lancé par une session Ollama précédente et occupe encore le GPU : quitte Ollama depuis son icône de la barre des tâches, termine ce processus, relance Ollama (vu sous Windows après un redémarrage d'Ollama pendant un long test) |
| « llama-server not found » ou « model file not found » | tu as choisi llama.cpp pour un modèle : installe-le ou corrige le chemin (`readscout engine`), ou reviens à Ollama avec `readscout engine ollama` |
| llama.cpp est plus lent qu'Ollama sur un GPU NVIDIA | `readscout doctor` liste les périphériques que voit llama-server : avec seulement `Vulkan0` ou sans GPU, prends le build CUDA |
| llama.cpp répartit le modèle sur ton GPU intégré | `readscout engine llamacpp --args "--device CUDA0"` (l'identifiant que `doctor` affiche pour ton GPU) |
| L'agent n'utilise jamais readscout | redémarre l'agent après l'installation ; `readscout doctor` vérifie la connexion |
| Réponses lentes | normal pour le gros modèle sur une petite carte (20 à 60 s) ; le petit répond en quelques secondes |

## Sécurité, limites, désinstallation

- Les modèles tournent uniquement sur `127.0.0.1` ; les modèles cloud d'Ollama sont refusés (par leur nom et quand Ollama
  les signale comme servis à distance), jamais de modèle en ligne. Avec llama.cpp (facultatif), readscout lance
  `llama-server` lui-même sur `127.0.0.1`, sur un port libre et avec une clé secrète aléatoire (une page web ne peut
  donc pas l'interroger), uniquement pour les fichiers `.gguf` que tu as choisis. Le modèle n'a aucun outil ; seul
  readscout lit les fichiers, et seulement ceux que ton agent désigne. Par défaut, ça peut être n'importe quel dossier
  (rien à enregistrer). `.env*`, `.git`, clés, fichiers d'identifiants et binaires sont toujours refusés (majuscules
  comprises) ; les secrets courants sont masqués (clés de fournisseurs, JWT, mots de passe dans les URL, en-têtes
  `Authorization`, affectations `password`/`secret`/`token`...), et `local_edit` refuse les fichiers qui en contiennent.
  Le masquage repose sur des motifs : aucun n'est parfait, garde les vrais identifiants hors de tes projets.
  `local_edit` écrit de façon atomique, n'écrase jamais un fichier modifié pendant l'attente du modèle, et ne restaure
  que ce qu'il a écrit ; ses commandes `gate` s'exécutent avec tes droits, choisies par l'agent.
- **Si tu restreins ton agent** (Bash interdit, `Read` limité à certains dossiers dans les permissions de Claude Code),
  readscout ne voit pas ces règles : il lit ce que l'agent lui désigne et exécute ses commandes `gate`. Pour garder les
  mêmes limites : `readscout folders add <dossier>` (les modèles ne lisent et n'écrivent plus que dans ces dossiers ;
  `readscout folders` affiche la liste, `readscout folders remove <dossier>` en retire un) et `readscout gate off`
  (`local_edit` refuse alors toute commande `gate`). `readscout doctor` affiche les deux réglages.
  Sont stockés en local : `config.json` et `metrics.jsonl` (outil, modèle, tailles, durées ; jamais de contenu), et avec
  llama.cpp `llamacpp.json` (processus, port et dernier usage du serveur) et `llama-server.log` (chargement et durées,
  jamais de contenu).
  Détails : [SECURITY.md](SECURITY.md).
- Une citation vérifiée prouve que la ligne existe, pas que le modèle l'a bien comprise. Ne délègue ni revue de code,
  ni recherche de bugs, ni vérification de faits.
- Désinstaller : `readscout uninstall-agent claude` (ou `/plugin uninstall readscout@readscout`),
  `readscout uninstall-agent codex`, puis `uv tool uninstall readscout`. Les modèles restent dans Ollama (`ollama rm`).

Commandes, modèles et résultats détaillés : [README.md](README.md) et [docs/BENCHMARK.md](docs/BENCHMARK.md).

## Licence

[MIT](LICENSE)
