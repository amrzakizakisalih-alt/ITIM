# Architecture du Backend ITIM v2

## Vue d'ensemble

Le backend est un **tuteur intelligent (ITS)** structuré en packages Python par domaine :

```
app/          →  Présentation & orchestration (FastAPI, WS, routes)
core/         →  Infrastructure partagée (LLM, DB, utilitaires)
domain/       →  Logique métier (maths, cognition, exercices)
input/        →  Entrées utilisateur (strokes, gestes)
tutor/        →  Orchestration pédagogique
```

## Packages

### `app/` — Présentation & Orchestration

| Fichier | Rôle |
|---------|------|
| `main.py` | Point d'entrée FastAPI (≈80 lignes). Crée l'app, configure CORS, instancie les singletons et enregistre les routes. |
| `session.py` | `SessionState` et `session_states` : fabrique d'état par connexion WS. |
| `intervention.py` | Boucle proactive asynchrone (`intervention_loop`). |
| `ws_handlers.py` | Gestionnaire WebSocket unique (`/ws`). Dispatch des messages et délégation au `Tutor`. |
| `api_routes.py` | Endpoints REST d'administration (buggy-rules, exercises, health, SPA fallback). |

### `core/` — Infrastructure

| Fichier | Rôle |
|---------|------|
| `llm_client.py` | Client unifié Groq / OpenAI / Ollama. Texte + vision (`image_to_latex`). |
| `connection_manager.py` | Gestion des connexions WebSocket (broadcast, déconnexion). |
| `persistence.py` | Classe de base `SQLiteStore` factorisant le CRUD SQLite. |
| `json_utils.py` | `extract_json()` : extraction robuste de JSON depuis une réponse LLM. |
| `profile_manager.py` | Persistance du profil étudiant entre sessions (chunks ACT-R). |

### `domain/math/` — Domaine Mathématique

| Fichier | Rôle |
|---------|------|
| `math_expert.py` | Expertise mathématique : SymPy, buggy rules, AST, comparaison d'étapes. |
| `math_processor.py` | Rendu strokes → image PIL (crop + upscale) et OCR pix2tex. |
| `step_tracker.py` | Suivi étape par étape d'un exercice (vérification, skip, progression). |
| `ast_utils.py` | Conversion SymPy ↔ AST générique et matching structurel. |

### `domain/cognitive/` — Domaine Cognitif

| Fichier | Rôle |
|---------|------|
| `act_r.py` | Façade cognitive unifiée. Ordonnance `StudentModel` et `MathExpert`. |
| `student_model.py` | Mémoire déclarative ACT-R (chunks, knowledge tracing) + indicateurs comportementaux. |
| `dialogue_manager.py` | Historique des messages de la session. |
| `pedagogical_agent.py` | Décisions pédagogiques (hint, intervention, difficulté). |

### `domain/exercises/` — Domaine Exercices

| Fichier | Rôle |
|---------|------|
| `exercise_generator.py` | Génération d'exercices via LLM + vérification SymPy. |
| `exercise_library.py` | Bibliothèque persistante d'exercices (SQLite, recherche, validation). |
| `document_processor.py` | Extraction de concepts mathématiques depuis un document texte. |
| `buggy_rule_learner.py` | Apprentissage incrémental des règles d'erreur (découverte, vote, persistance). |

### `input/` — Entrées Utilisateur

| Fichier | Rôle |
|---------|------|
| `stroke_buffer.py` | Accumulation et clustering spatial des strokes. |
| `stroke_analyzer.py` | Détection de frustration via l'analyse des strokes. |

### `tutor/` — Orchestration Pédagogique

| Fichier | Rôle |
|---------|------|
| `tutor.py` | Porte-parole pédagogique unique. Parse les intentions, orchestre `PedagogicalAgent` et `DialogueManager`, interroge `ActR`. |

## Flux de données principal

1. **Strokes manuscrits** → `input.stroke_buffer` + `input.stroke_analyzer`
   → Auto-OCR différé (`domain.math.math_processor` / `core.llm_client`) → `domain.math.step_tracker`
2. **Messages texte** → `tutor.tutor` → parsing d'intention → `domain.cognitive.act_r` (AST + buggy rules)
   → réponse LLM contextualisée via `core.llm_client`
3. **Document importé** → `domain.exercises.document_processor` → `domain.exercises.exercise_generator`
   → `domain.exercises.exercise_library`
4. **Soumission mathématique** → `domain.math.math_expert.compare_steps_async()`
   → `domain.cognitive.pedagogical_agent.decide_intervention()`

## Règles d'architecture

- **Une responsabilité = une classe.** `app/main.py` ne contient plus de logique métier.
- **Une source de vérité = une instance.** `MathExpert` est instancié une seule fois et injecté dans `ActR`.
- **Pas de code mort.** Les méthodes et classes non utilisées ont été supprimées.
- **Pas de duplication.** La persistance SQLite est factorisée dans `core.SQLiteStore`. Le parsing JSON LLM est factorisé dans `core.json_utils.extract_json()`.
- **Snake case pour les modules.** Conforme aux conventions PEP 8.
