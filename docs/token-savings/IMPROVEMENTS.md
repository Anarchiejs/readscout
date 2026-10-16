# Plan d'amélioration : réduction des tokens de l'agent

Liste de 100 pistes ramenée à des lots de travail ordonnés. Chaque point retenu garde son numéro d'origine entre crochets, par exemple **[44]**. La section finale liste les points non retenus et la raison.

Conventions : « Fichiers » désigne ce que j'ai vérifié (`tasks.py`, `text.py`) ou une zone à localiser (marquée *à localiser*). « Critère » est la condition de réussite mesurable du lot.

## Ordre d'exécution

| Ordre | Lot | Nature | Dépend de |
|---|---|---|---|
| 1 | A. Citations et reçus | Corrections de bugs | rien |
| 2 | B. Skill allégé | Gain sûr, sans infrastructure | rien |
| 3 | I. Instrumentation minimale | Mesure | rien |
| 4 | C. Reçus sans relecture | Protocole de réponse | A |
| 5 | E. Extracteurs déterministes | Plus gros levier | A, C, I |
| 6 | D. Journaux | Pipeline hybride | A, C |
| 7 | F. Complétude | Qualité des réponses locales | E |
| 8 | G. Allers-retours et contexte | Optimisation MCP | I |
| 9 | I (suite). Nouvelle campagne | Validation | tout |
| 10 | H. Caches | Seulement si sessions longues mesurées | E, I |

---

## Lot A. Citations et reçus (bugs à corriger d'abord)

### A1. Ne plus tronquer les citations vérifiées [44]
- **Constat vérifié** : `tasks.py:293` coupe à 87 caractères + `...`, puis `tasks.py:294` repasse la citation dans `_clean(q, 90)`, qui tronque encore. Le texte affiché n'est plus celui qui a été vérifié.
- **Comment** :
  1. Supprimer la ligne 293 et l'appel `_clean(q, 90)` pour les citations.
  2. Créer `_clean_quote(q)` qui retire seulement les caractères de contrôle (`[\x00-\x08\x0b-\x1f\x7f]`) et **ne réduit pas les espaces** (voir A5).
  3. Si une citation dépasse la limite d'affichage, ne pas la couper avec `...` : appliquer A6.
- **Test** : une citation vérifiée de 85 caractères ressort identique. Une de 200 caractères sort comme fragment exact (A6), jamais avec `...`.

### A2. Le serveur fournit le texte de la citation, pas le modèle [45]
- **Comment** :
  1. Dans le schéma de réponse locale, remplacer le champ « citation libre » par un emplacement : `path`, `line_start`, `line_end`, et éventuellement `col_start`/`col_end`.
  2. Après réponse, relire le fichier et extraire le texte exact à cet emplacement.
  3. Si le modèle fournit encore une citation, l'utiliser seulement pour retrouver l'emplacement (recherche dans la plage), puis la remplacer par le texte lu.
- **Test** : une réponse du modèle avec une citation légèrement altérée donne un reçu avec le texte exact du fichier.

### A3. Ajouter le chemin ou un identifiant de candidat au schéma local [46]
- **Constat** : les findings locaux contiennent une ligne mais pas de chemin. Une citation identique dans deux fichiers est ambiguë.
- **Comment** :
  1. Numéroter les candidats envoyés au modèle (`id: 1..n`, avec `path` et plage de lignes côté serveur).
  2. Faire renvoyer `candidate_id` dans chaque finding. Résoudre le chemin côté serveur.
  3. Rejeter (et compter dans `dropped`) tout finding dont l'id n'existe pas.
- **Test** : deux fichiers contenant la même ligne produisent deux findings distincts avec le bon chemin.

### A4. Ne pas masquer les références symboliques à des secrets [49] et garder le masquage des vraies valeurs [50]
- **Constat vérifié** : `text.py:18-20` (`ASSIGNED_SECRET`) masque toute valeur de 12 caractères ou plus après `apiKey:`. `process.env.OPENAI_API_KEY` fait 26 caractères et devient `[REDACTED]`.
- **Comment** :
  1. Ajouter à la fin du motif une exclusion en lookahead négatif sur le début de la valeur, pour les expressions de code qui désignent une source et non une valeur :
     `process.env.`, `import.meta.env.`, `os.environ`, `os.getenv(`, `getenv(`, `env(`, `Deno.env`, `System.getenv`, `ENV[`, `${`, `{{`, `config.`, `settings.`, `self.`, `this.`.
  2. Cas à traiter à part : une valeur qui ressemble à un identifiant pointé (`[A-Za-z_][\w]*(\.[A-Za-z_]\w*)+`) **sans chiffre ni mélange de casse aléatoire** est une expression, pas un secret. Une valeur avec chiffres et caractères mélangés reste masquée.
  3. Ne pas toucher `SECRET`, `URL_PASSWORD`, `AUTH_HEADER` : ils reconnaissent des formes de vraies valeurs.
- **Tests (les deux sens)** :
  - Doivent rester visibles : `apiKey: process.env.OPENAI_API_KEY`, `password = os.environ["DB_PASSWORD"]`, `token: ${GITHUB_TOKEN}`.
  - Doivent rester masqués : `apiKey: "sk-abc123def456ghi789jkl"`, `password = "Zx9!qL2mPw8Rt"`, `"secret": "a1B2c3D4e5F6g7"`.
  - Ajouter ces cas à la suite de tests existante.

### A5. Préserver les espaces significatifs [47] et distinguer exact et normalisé [48, 55]
- **Comment** :
  1. Dans la vérification de citation (`text.py`, *à localiser* : la fonction qui rapproche une citation du source), tester d'abord la correspondance **exacte** de sous-chaîne.
  2. Seulement en cas d'échec, tenter une correspondance normalisée (espaces réduits). Marquer le finding `match: "exact" | "normalized"`.
  3. En cas de `normalized`, renvoyer le texte du fichier (A2), pas celui du modèle.
  4. Dans l'en-tête du reçu, afficher les deux compteurs : `N exact, M normalized`.
  5. Documenter dans le reçu que « vérifié » signifie « la ligne existe », et non « le constat est exhaustif ou juste » **[55]**. Le résumé reste étiqueté « unverified » (déjà le cas).
- **Test** : une chaîne `"a  b"` (deux espaces) dans le fichier reste `"a  b"` dans le reçu.

### A6. Fragment exact quand la ligne est trop longue [51]
- **Constat** : deux citations finales du benchmark identifient la route d'upload mais en altèrent le code.
- **Comment** :
  1. Si la ligne dépasse la limite d'affichage, choisir une fenêtre contiguë de la ligne **centrée sur l'élément cherché** (position du premier terme du constat, sinon début de ligne).
  2. Renvoyer ce fragment avec ses colonnes (`path:ligne:col_début-col_fin`), sans `...` à l'intérieur du texte cité. Indiquer la troncature en dehors des guillemets : `(fragment, ligne de N caractères)`.
- **Test** : le fragment est une sous-chaîne exacte de la ligne source.

### A7. Format de sortie directement réutilisable [52] et métadonnées réduites [54]
- **Comment** :
  1. Pour les extractions structurées, une ligne par fait : `chemin:ligne | constat | citation`.
  2. Réduire l'en-tête (`tasks.py:285-287`) à une ligne courte : `[label · modèle · N citations · M écartées]`. Déplacer durée, taille lue et nombre de chunks dans la télémétrie, accessible mais hors reçu.
  3. Garder dans le reçu seulement ce qui change la décision du coordinateur : écartées, tronquées, plafond atteint, erreurs.
- **Critère du lot A** : zéro `...` dans une citation vérifiée, zéro `[REDACTED]` sur une référence `process.env.*`, reçu plus court d'au moins 30 % en caractères d'en-tête.

---

## Lot B. Skill allégé

### B1. Décider selon le travail évité [1], voie directe pour les recherches simples [2], cas à ne pas déléguer [3]
- **Comment** : ajouter au début de `src/readscout/skill/SKILL.md` un bloc de décision de 5 lignes maximum :
  - **Ne pas déléguer** : la réponse tient dans un `rg` (nom de variable, fonction ou middleware cité explicitement) ; ou une lecture complète courte sera de toute façon nécessaire ensuite (exemple mesuré : FastAPI, +39 705 tokens pour le même F1).
  - **Déléguer** : plusieurs lectures nécessaires pour peu de faits ; journal long ; extraction sur nombreux fichiers.
- **Test** : relire 6 traces de tâches simples et vérifier que ce bloc suffit à décider sans charger le reste.

### B2. Raccourcir le cœur [5], sortir `local_edit` [6], sortir le dépannage [7]
- **Comment** :
  1. Découper `SKILL.md` en cœur (règles de choix et d'usage correct des outils de lecture) et références : `references/local_edit.md`, `references/troubleshooting.md`, `references/how-it-works.md`.
  2. Dans le cœur, une ligne par référence : « pour modifier des fichiers, lire references/local_edit.md ».
  3. Objectif : passer d'environ 5 820 caractères à moins de 2 500 pour le cœur.
  4. Vérifier que les règles `AGENTS.md` du projet restent dans le cœur **[10]** (on ne les supprime pas pour améliorer le score).
- **Test** : un script compte les caractères du cœur et échoue au-delà du budget.

### B3. Description de découverte [8]
- **Comment** : réécrire le champ `description` du frontmatter pour dire quand **ne pas** utiliser le skill (« un grep direct suffit pour une variable, une fonction ou un middleware nommé ») en plus de quand l'utiliser. 300 caractères maximum.
- **Test** : sur les 15 tâches du benchmark, relever celles où la description seule aurait suffi à écarter le skill.

### B4. Regrouper les découvertes obligatoires [10]
- **Comment** : documenter dans le cœur un seul premier appel qui lit `AGENTS.md` et liste les fichiers utiles, au lieu de trois appels. Ne jamais supprimer la lecture de `AGENTS.md`.

### B5. Ne pas chercher à augmenter les appels [4]
- Règle de conception, pas une tâche : onze tâches B n'utilisent pas readscout et c'est correct quand B1 s'applique. Ne pas ajouter d'incitation à appeler l'outil.

**Critère du lot B** : cœur du skill sous 2 500 caractères ; aucun usage de `local_edit` chargé sur une tâche de lecture ; aucune baisse de F1 sur la campagne suivante.

---

## Lot I. Instrumentation et campagne (mesure d'abord)

### I1. Mesures minimales à ajouter avant les gros chantiers
- **Usage par requête d'inférence [79]** : enregistrer l'usage de chaque requête, pas seulement `turn.completed` agrégé. *À localiser* : le point où le harnais lit les compteurs Codex.
- **Contenu réellement transmis après troncature [80]** : mesurer ce que le client injecte au modèle, pas les caractères de sortie shell brute.
- **Coûts séparés [81]** : étiqueter chaque étape (découverte, skill, reçu, vérification, repli, réponse finale).
- **Taux de relecture après délégation [82], doubles lectures [18]** : pour chaque appel readscout, comparer les `path:lignes` retournés avec les lectures Codex ultérieures de la même plage. Indicateur central du produit.
- **Actions et requêtes modèle distinguées [64]** : compter séparément les actions shell/MCP et les requêtes d'inférence.
- **Texte et contenu structuré MCP [68, 69]** : vérifier ce que le client injecte (texte, structuré ou les deux). Ne pas retirer la représentation textuelle : la spécification MCP 2025-06-18 recommande de la garder avec le contenu structuré. L'optimisation vise la consommation côté client.
- **Complétude locale vs finale [83]** : enregistrer le résultat local avant toute réparation par Codex, pour savoir si un bon F1 final vient du local ou d'une reprise.
- **Chargement vs inférence locale [87]** : deux horodatages distincts.

### I2. Correction du scorer [84]
- **Comment** : accepter les occurrences valides de variables citées dans un autre fichier. Publier la correction comme **nouvelle version du protocole** (`docs/token-savings/PROTOCOL.md`), sans réécrire les anciens résultats : recalculer les anciens runs à part, avec les deux versions affichées.

### I3. Vérifications sémantiques [85]
- **Comment** : pour les routes, vérifier méthode HTTP, chemin et description, pas seulement la ligne. Ajouter au scorer un contrôle champ par champ.

### I4. Méthode de campagne
- **Suivi par famille [86]** : tableau séparé pour questions négatives, listes exhaustives, journaux, localisation.
- **Ablation [88]** : trois configurations (déterministe seul, modèle local seul, hybride).
- **Validations sans quota agent [89]** : parseurs, formats, filtres, citations et transport testés avec `pytest` avant toute campagne payante.
- **Jeu hors optimisation [91]** : réserver au moins 8 tâches non utilisées pour développer les extracteurs.
- **Répétitions [90]** : uniquement dans une campagne dont le budget est écrit dans le protocole avant lancement (nombre de répétitions, tokens maximum).
- **Deux moyennes [93]** : total pondéré et moyenne par tâche, avec gains, pertes et replis.
- **Contraintes de qualité [94]** : un résultat de tokens n'est publié qu'avec exactitude, citations vérifiées et résultats incomplets visibles.
- **Parcours réels [92]** : série de questions successives sur un même dépôt, publiée **séparément** du benchmark actuel.
- **Choix de modèle selon la session complète [61, 60]** : critère combiné tokens Codex + qualité finale + taux de repli + durée ; évaluer aussi la stratégie de réparation, pas seulement le premier modèle.
- **Estimation vs économie mesurée [100]** : conserver la séparation. Ne pas modifier le diviseur de l'estimation pour rapprocher un chiffre.

**Critère du lot I** : le rapport de campagne attribue chaque token à une étape et donne le taux de relecture.

---

## Lot C. Reçus qui évitent la relecture

### C1. Vérifier les lignes citées au lieu de relancer une recherche globale [11, 12]
- **Comment** : ajouter au cœur du skill (B2) la règle « après un reçu, ouvrir seulement les lignes citées (`sed -n 'a,bp'`), jamais relancer une recherche large ». Interdire dans le skill les motifs larges (`timeout`, `WARN`, `503`, `unhealthy`) et demander une vérification ciblée de la cause et de ses conséquences.
- **Mesure** : taux de relecture (I1) sur le grand journal ; cible : disparition de la sortie shell d'environ 165 000 caractères.

### C2. Retourner le petit contexte de vérification [13]
- **Comment** : option `context_lines` (défaut 2) : chaque finding renvoie sa citation plus 2 lignes avant et après, lues dans le fichier (jamais produites par le modèle). Plafonner le total par reçu.

### C3. Un seul reçu avec tous les éléments demandés [14]
- **Comment** : pour les journaux, schéma de sortie imposé : `cause_initiale`, `consequences[]` (distinctes), `etat_final`. Un champ vide doit être explicite (`null` avec raison), pas absent.

### C4. Recherche et analyse dans le même appel [15]
- **Comment** : accepter dans `local_ask`/`local_digest` un paramètre `pattern` ou `glob` qui fait la sélection de candidats côté serveur, puis l'analyse. Supprimer le parcours « lister, demander, rechercher à nouveau ».

### C5. États complet, partiel, indéterminé [16] et repli limité aux inconnus [17]
- **Comment** :
  1. Champ `status: complete | partial | undetermined` dans le reçu.
  2. En cas de `partial` ou `undetermined`, champ `remaining: [{path, symbol|lines}]` listant exactement ce que Codex doit vérifier.
  3. Le skill dit : traiter seulement `remaining`, ne pas reprendre le reste.

### C6. Stratégie de sortie après un échec local [20]
- **Comment** : règle du skill : au plus **une** relance reformulée ; au deuxième échec, passer à la lecture directe ciblée sur `remaining`. Pas de boucle « redemander, relire, reformuler ».

### C7. Vérification adaptée, pas systématique [19]
- **Comment** : le cœur du skill décrit trois niveaux : localisation simple (aucune vérification au-delà du reçu), extraction (vérifier un échantillon de lignes), décision sensible (revue complète). Pas de vérification globale par défaut.

**Critère du lot C** : taux de relecture après délégation divisé par deux sur les tâches journaux et extraction, sans baisse de F1.

---

## Lot E. Extracteurs déterministes pour le code (levier principal)

Principe commun **[39]** : extraction syntaxique pour les faits reconnaissables, modèle local pour les cas résiduels, coordinateur pour les décisions. Chaque extracteur renvoie `status` (C5), le nombre d'unités reconnues et les constructions non reconnues **[40, 41]**.

### E0. Cadre commun
- **Comment** :
  1. Nouveau module `extractors/` (*à localiser* dans `src/readscout/`) avec une interface commune : `extract(path, text) -> list[Fact]`, `Fact = {path, line_start, line_end, kind, name, evidence_text}` (`evidence_text` relu dans le fichier, comme A2).
  2. Utiliser `ast` (Python) et `tree-sitter` ou à défaut des expressions régulières balancées (JS/TS). Choisir selon la dépendance acceptable pour le projet : décision à valider avant d'écrire du code.
  3. Découper selon les unités du code **[42]** : jamais séparer un décorateur de sa fonction, ni une déclaration de route de ses middlewares.
  4. Rapport de couverture **[41]** : fichiers parcourus, unités reconnues, unités ignorées avec la raison.
  5. Constructions non reconnues **[40]** : imports dynamiques, alias complexes, wrappers inconnus listés dans `unrecognized`, ce qui force `status: partial`.
  6. Déduplication par objet demandé **[53]** : variable d'environnement par nom, route par (méthode, chemin), accès table par (table, opération). Conserver toutes les occurrences en liste de positions.

### E1. Variables d'environnement [31]
- **Comment** : reconnaître `process.env.X`, `process.env["X"]`, `os.environ["X"]`, `os.environ.get("X")`, `os.getenv("X")`, `import.meta.env.X`, `Deno.env.get("X")`, plus les alias reconnus (`const { X } = process.env`, `env = os.environ`). Dédupliquer par nom, garder la liste des positions.
- **Cas non reconnus** : `process.env[nom_dynamique]` signalé comme `unrecognized`.

### E2. Routes Express et middlewares [32]
- **Comment** : reconnaître `app|router.METHOD(path, ...handlers)` et les chaînes `router.route(path).get(...).post(...)`. Chaque handler précédent le dernier est un middleware. Suivre `app.use(path, router)` pour composer les préfixes quand le routeur est dans le même fichier ; sinon signaler le préfixe comme inconnu.

### E3. Endpoints Python [33, 35]
- **Comment** : via `ast`, pour chaque fonction décorée par `@app.get|post|...`, `@router.*`, renvoyer décorateur, signature complète et **dépendances** (`Depends(...)`, paramètres annotés). Inclure aussi les dépendances posées sur le routeur (`APIRouter(dependencies=[...])`, `include_router(..., dependencies=[...])`) **[35]**.

### E4. Inventaire avant réponse négative [34] et propriété décrite précisément [36]
- **Comment** :
  1. Pour une question « quels endpoints n'ont pas X », construire d'abord l'inventaire complet (E3), puis filtrer.
  2. Formuler le constat avec son périmètre : « aucun paramètre `CurrentUser` dans les N endpoints analysés de tel module », jamais « l'API est publique ».

### E5. Accès Supabase [37]
- **Comment** : reconnaître `.from("table")` et la chaîne d'opérations qui suit (`.select`, `.insert`, `.update`, `.delete`, `.upsert`, `.rpc`) même sur plusieurs lignes, en s'appuyant sur l'arbre syntaxique plutôt que sur une ligne.

### E6. Localisation lexicale [38]
- **Comment** : si la question contient un symbole ou un commentaire discriminant, renvoyer directement le résultat de `rg` structuré (chemin, ligne, texte), sans modèle. Seuil : au plus N correspondances (par exemple 20) ; au-delà, passer au modèle.

### E7. Tests hors benchmark [43]
- **Comment** : construire des mini-dépôts de test (une dizaine de fichiers par langage) avec des variantes de syntaxe : alias, ordre des middlewares, chaînes multilignes, décorateurs empilés, imports dynamiques. Les extracteurs sont validés sur ces variantes et sur le jeu réservé (I4), jamais ajustés sur les noms des quatre dépôts du benchmark.

**Critère du lot E** : sur les tâches d'extraction, au moins 80 % des unités du jeu hors benchmark reconnues, 100 % des constructions non reconnues signalées, aucune relecture complète par Codex pour les tâches couvertes.

---

## Lot D. Journaux

### D1. Voie déterministe et séparation extraction/interprétation [21, 22]
- **Comment** :
  1. Étape 1 (code) : repérer les événements d'erreur et d'avertissement, leurs positions, leurs niveaux, et regrouper en unités.
  2. Étape 2 (modèle local, seulement si nécessaire) : expliquer les relations ambiguës entre unités déjà isolées.
  3. Si l'étape 1 suffit à répondre (erreurs distinctes avec contexte), ne pas appeler le modèle.

### D2. Déduplication qui préserve les occurrences [23, 24, 25]
- **Constat** : le préfiltrage actuel normalise les nombres, ce qui fusionne des événements portant sur des ressources différentes.
- **Comment** :
  1. Clé de regroupement : message normalisé **plus** identifiants extraits (requête, worker, transaction, ressource, hôte, port).
  2. Pour chaque groupe, conserver : premier événement (ligne), dernier événement (ligne), nombre d'occurrences, liste des identifiants distincts (bornée).
  3. Ne jamais afficher toute la série.

### D3. Traces multilignes comme unités [26]
- **Comment** : détecter le début d'une trace (`Traceback`, `Exception in`, `at ` suivi de lignes indentées, `Caused by:`) et prendre le bloc entier jusqu'à la première ligne sans indentation ou avec horodatage. Remplacer la fenêtre fixe autour de `ERROR`.

### D4. Chronologie et causalité [27]
- **Comment** : le schéma de sortie sépare `first_seen` (ordre chronologique, fait vérifiable) et `likely_cause` (interprétation, avec `confidence: certain | probable | uncertain`). Une interprétation incertaine reste marquée.

### D5. Extraits de début et de fin bornés [28] et rapport du filtre [29]
- **Comment** :
  1. Début et fin : 5 lignes chacun au maximum, plafond configurable.
  2. Ajouter au reçu : `kept: N lignes / écartées: M ; niveaux conservés ; motifs exclus`. Cela permet au coordinateur de décider s'il vérifie davantage.

### D6. Petits journaux [30]
- **Comment** : mesurer, ne pas fixer de règle. Sur le journal de 67 Ko (+27 % en B), tester la voie déterministe seule. N'introduire un seuil que s'il se confirme sur plusieurs journaux du jeu réservé.

**Critère du lot D** : sur le grand journal, plus de relecture globale ; sur le petit journal, surcoût B inférieur à celui de la campagne précédente.

---

## Lot F. Complétude des réponses locales

### F1. Plafonds cohérents [56] et budget de sortie adapté [57]
- **Constat** : le schéma plafonne à `MAX_FINDINGS` (30) par chunk ; `max_items` ne gouverne que l'affichage (`tasks.py:291`). Les relever séparément ne suffit pas.
- **Comment** :
  1. Une seule source de vérité : `max_items` pilote aussi `MAX_FINDINGS` et le schéma.
  2. `max_tokens` de sortie calculé à partir du nombre de candidats connus (E0) : `base + k × candidats`, avec un plafond de sécurité.

### F2. Vérification locale de couverture [58] et relance ciblée [59]
- **Comment** :
  1. Après réponse, comparer l'inventaire (E0) aux findings.
  2. Pour les candidats manquants, une seule relance bornée contenant uniquement ces candidats.
  3. Ce qui reste manquant va dans `remaining` (C5).

### F3. Pas d'indice de complétude inventé par le modèle [63] et pas de confiance dans la taille [62]
- **Comment** : supprimer `complete: true` et le nombre annoncé du schéma, ou les ignorer quand un inventaire structurel existe. `status` est calculé par le serveur. Le cas FastAPI (modèle 26B, reprise nécessaire) montre qu'un modèle plus grand ne garantit pas la complétude.

**Critère du lot F** : sur les listes exhaustives, le serveur détecte 100 % des omissions du modèle avant d'envoyer le reçu.

---

## Lot G. Allers-retours et contexte répété

### G1. Regrouper et réduire côté serveur [65, 71]
- **Comment** : le serveur fait déjà un reduce par morceaux (`tasks.py:259`). S'assurer qu'une question sur un dossier entier se termine en un seul appel MCP, et assembler les constats directement depuis les données structurées sans étape de résumé supplémentaire.

### G2. Borner la sortie par tâche [66]
- **Comment** : pas de contexte général ni de preuves redondantes dans le reçu. Un plafond de caractères total, avec message explicite s'il est atteint.

### G3. Regroupement des opérations indépendantes [64]
- **Comment** : instruire dans le skill de grouper les lectures indépendantes dans un seul appel shell. Mesurer d'abord (I1) si les 35 actions B contre 28 pour A correspondent à des requêtes modèle distinctes.

**Critère du lot G** : moins de requêtes d'inférence par tâche, mesuré par requête, sans perte de qualité.

---

## Lot H. Caches (différé)

À entreprendre seulement si les mesures de parcours réels (I4, [92]) montrent un bénéfice. Quand ce sera le cas :

- **Cache par empreinte de contenu [73]** : clé = hash du fichier ; invalidation à tout changement.
- **Inventaire réutilisé [74]** : routes, fonctions et positions partagés entre extractions.
- **Contexte dans la clé [75]** : périmètre, configuration, version de l'extracteur, règles de masquage.
- **Dépendances invalidées [76]** : un routeur importé modifié invalide les fichiers qui en dépendent.
- **Périmètre autorisé [77]** : indexer seulement les dossiers de la liste d'autorisation.
- **Distinction des caches [78]** : cache local (évite le travail) et cache d'entrée de l'agent (ne réduit pas la métrique actuelle, qui inclut les tokens en cache).
- **Réutilisation du skill en session longue [9]** : mesurable seulement avec des sessions longues (I4).
- **Expansion ciblée par identifiant [67]** : à tester seulement si elle ne crée pas plus d'allers-retours qu'elle n'en économise.

---

## Contraintes permanentes (ne sont pas des tâches) [95-99]

- Latence du moteur local : à optimiser pour l'usage, sans compter dessus pour réduire les tokens de l'agent **[95]**.
- Contexte local plus grand : seulement si une mesure montre moins d'erreurs ou d'étapes **[96]**.
- Déchargement automatique des modèles conservé **[97]**.
- Garde-fous d'accès et de confidentialité conservés : les économies viennent de l'extraction, pas de leur affaiblissement **[98]**.
- Contrôles d'isolation et d'exécution du harnais conservés **[99]**.

---

## Points non retenus et raison

| Point | Raison |
|---|---|
| [70] Profil de lecture léger | Le contrôle trivial ne montre que 144 tokens de surcoût : gain trop faible pour un chantier. À revoir après le lot B. |
| [72] Ne pas se concentrer sur les tokens de sortie | Constat (environ 1,25 % du total B), pas une action. Appliqué implicitement : aucun lot ne cible la sortie. |
| [9] Réutiliser le skill en session longue | Non mesurable avec les sessions indépendantes : déplacé au lot H. |
| [67] Expansion ciblée | Risque d'ajouter des allers-retours : déplacé au lot H. |
| [73-78] Caches | Gain non démontré : lot H, différé. |
| [60, 61, 92, 93, 94, 100] | Retenus mais fusionnés dans le lot I (méthode de campagne). |
| [3, 4, 19, 30] | Retenus comme règles de décision (B1, B5, C7, D6), pas comme chantiers. |
| [95-99] | Contraintes permanentes, pas des tâches. |

### Doublons fusionnés

- [16] et [17] : un seul mécanisme `status` + `remaining` (C5).
- [21] et [22] : une seule voie déterministe puis interprétation (D1).
- [58] et [59] : couverture puis relance ciblée (F2).
- [63] et [41] : `status` calculé par le serveur (F3, E0).
- [47], [48], [55] : correspondance exacte/normalisée (A5).
