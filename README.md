# Desk

A simulated junior dev team for learning to program. It reviews your code, keeps track of what you keep getting wrong, and decides what you should do next.

![Dashboard](docs/img/dashboard.png)

**Status:** research prototype. All services, the client and the agent pipelines are implemented and unit-tested, but nothing has been evaluated with real students yet. What I have measured is how the pieces behave in tests and in simulation. The [limitations](#limitations) section says what that does and does not show.

The interface is in Russian. Screenshots use sample data.

## What it is

A student picks a track (backend, frontend or fullstack) and a level. They get a project split into sprints, and each sprint is a kanban board. They write code in the browser and submit it. A pipeline of LLM agents and deterministic checks reviews the submission against acceptance criteria. Each task allows two attempts by default. Four AI teammates (product, analytics, QA, tech lead) answer questions in a chat.

Between tasks, a knowledge model built from the review outcomes decides what happens next: fix one specific criterion, ask one specific teammate, repeat a skill that is fading, or take a particular task from the board. At the end of a sprint the student gets a performance-review letter with a grade and salary change. The whole thing is meant to feel like the first months of a job.

It is about 27,000 lines of Python (five services) and 6,400 lines of TypeScript, with 243 unit tests.

## Four things worth a look

1. **A reviewer that cannot grade by feel.** The final score is computed. The LLM agents fill in a rubric, and the number comes from the rubric pass rate, capped by hard evidence: broken syntax, failing tests, objections from a second reviewer, skipped steps in the process. An agent cannot talk its way past a cap. See [the review pipeline](#the-review-pipeline).

2. **Knowledge tracing on top of LLM review output.** Each acceptance criterion is mapped to one or two of 14 skills. A Bayesian knowledge tracing model with forgetting turns pass/fail outcomes into a per-skill estimate, and a planner turns that into a next step. I derived the model parameters from behavioural constraints instead of picking them by hand. See [the learning trajectory](#the-learning-trajectory), and [docs/trajectory.md](docs/trajectory.md) (in Russian) for the full derivation.

3. **The agents are audited too.** Every review and every chat turn records which steps ran. A process check lowers the score if required steps were skipped, and flags a mentor reply that pastes a complete solution.

4. **The domain carries the motivation.** Grades, salary, a bonus that can be spent on extra help, a Friday demo, a night incident, and a peer-review task where the student finds a planted bug in code written by an LLM. What the student is shown depends on their grade. See [the career layer](#the-career-layer).

## Screens

The report after a submission. The score is on the left; the trajectory block says which skill to work on, why, and in which order.

![Review report](docs/img/review-report.png)

The team chat. The briefing at the top comes from the trajectory, so the teammates start from the same picture of the student.

![Team chat](docs/img/team-chat.png)

## Architecture

```mermaid
flowchart TB
    UI["<b>React client</b><br/>Vite, Monaco editor"] --> GW["<b>api_gateway</b><br/>routing, rate limit<br/><i>Redis</i>"]
    GW --> US["<b>user_service</b><br/>accounts, roles<br/><i>MongoDB, Redis</i>"]
    GW --> TS["<b>task_service</b><br/>projects, board, career<br/><i>MongoDB, Redis</i>"]
    GW --> SS["<b>submission_service</b><br/>reviews, trajectory<br/><i>MongoDB</i>"]
    GW --> AS["<b>agent_service</b><br/>review, chat, memory<br/><i>MongoDB, Redis, Chroma</i>"]
    TS -.->|HTTP| SS
    AS -.->|HTTP| SS
    US <--> K{{"Kafka"}}
    TS <--> K
    SS <--> K
    AS <--> K
    AS --> LLM["OpenAI-compatible<br/>LLM API"]
```

| Service | Owns | Notes |
|---|---|---|
| `api_gateway` | Routing of `/api/{user,task,submission,agents}`, rate limiting, sticky balancing | Redis fixed-window limiter, hash-based sticky routing |
| `user_service` | Accounts, access and refresh tokens, sessions, admin roles | Sessions and role cache in Redis |
| `task_service` | Project templates, sprints, the board, the close gate, career state | Read-through Redis cache in front of Mongo |
| `submission_service` | Submissions, the attempt limit, review results, the learning trajectory | Keeps a local cache of task status and description, fed by events |
| `agent_service` | The review graph, the team chat graph, memory, offline evals | LangGraph, ChromaDB, Langfuse tracing (optional) |

Events go over Kafka. Topic names come from settings.

| Event | Producer | Consumer | Why |
|---|---|---|---|
| user registered, profile updated | `user_service` | `task_service` | Keeps the student's direction and level next to their projects |
| task created, status updated | `task_service` | `submission_service` | Lets submissions be validated without a call back to `task_service` |
| submission created | `submission_service` | `agent_service` | Starts a review |
| submission reviewed | `agent_service` | `submission_service` | Stores the review |

Each service is layered as presentation, application (use cases and ports written as `Protocol`s) and infrastructure, and wired with [dishka](https://github.com/reagento/dishka). The rules that matter most, meaning scoring, the trajectory model, the close gate and the career rules, are plain functions with no I/O, so they are tested without any infrastructure.

## Life of a submission

```mermaid
sequenceDiagram
    autonumber
    actor S as Student
    participant SS as submission_service
    participant K as Kafka
    participant AS as agent_service
    participant TS as task_service

    S->>SS: POST /submissions (code)
    Note over SS: task open? no pending review?<br/>attempts left?
    SS->>K: submission created
    SS-->>S: 201, status pending
    K->>AS: submission created
    Note over AS: review graph,<br/>checkpointed in Redis
    AS->>K: submission reviewed
    K->>SS: submission reviewed
    Note over SS: store the review (idempotent)
    S->>SS: GET /submissions/me/trajectory
    Note over SS: replay reviews,<br/>update skill estimates
    SS-->>S: next action, focus skill, plan
    S->>TS: close the task, finish the sprint
    TS->>SS: HTTP: trajectory, reviews
    TS-->>S: allowed or not, with the reason
```

Some details that took a while to get right:

- **One pending review per task, even under a race.** If two submissions arrive at once, the one with the smaller id survives and the other is deleted.
- **Failures are counted fairly.** An infrastructure failure before the review started does not use up an attempt. A review that ran and failed does.
- **Reviews survive restarts.** The review graph is checkpointed in Redis under a key built from the submission, the attempt and a hash of the code. A redelivered Kafka message resumes from the last finished node or reuses a finished result. If the checkpoint store itself fails, the run stops instead of silently starting over.
- **Kafka consumers commit offsets by hand, with retries**, and applying a review result twice has no effect.

## The review pipeline

```mermaid
flowchart TD
    T["<b>tools</b><br/>AST checks, py_compile or node --check,<br/>optional sandboxed pytest"]
    A["<b>acceptance_rubric</b><br/>3 to 6 checkable criteria from the brief"]
    RB["<b>reviewer_bug</b><br/>reviewer and QA agents, run concurrently"]
    G["<b>grade_rubric</b><br/>each criterion marked pass or fail"]
    ADV["<b>adversarial</b><br/>a second reviewer looks for<br/>what the team missed or inflated"]
    SC["<b>scorecard_draft</b><br/>score computed from rubric and caps"]
    MP{"<b>mentor_plan</b>"}
    M1["<b>mentor_single</b>"]
    M3["<b>mentor_multi</b><br/>up to 3 drafts, best one selected"]
    PE["<b>process_eval</b><br/>required steps ran?<br/>no full solution in the reply?"]
    F["<b>finalize</b><br/>final score, save to memory"]

    T --> A --> RB --> G --> ADV --> SC --> MP
    MP -->|"clean case"| M1
    MP -->|"failed criteria, low score,<br/>objections, broken tools"| M3
    M1 --> PE
    M3 --> PE
    PE --> F
```

The score is not something a model writes. It is built like this:

```
task, reliability      integers 1..10 from the reviewer and the QA agent
base                   weaker + (stronger - weaker) // 4
rubric score           1 + round(9 * share of criteria passed)
final                  min(base, rubric score, every applicable cap)
```

| Cap | Trigger |
|---|---|
| 2 | Syntax or compilation fails |
| 4 | Tests run in the sandbox and fail |
| 5 | Two or more error-level findings from the tools |
| 5 or 7 | Half or more of the required criteria fail, or some of them fail |
| 5 or 7 | The adversarial reviewer objects with high or medium severity |
| 5 | The process check finds a pasted full solution, or three or more violations |
| 6 | The process check finds that the tools or the sandbox were bypassed |

The adversarial reviewer has deterministic rules of its own. They replace its verdict when the LLM call fails, and they override an LLM that agrees with the team when the rules see a high-severity contradiction, for example a top score for code that does not compile. The tool report also carries earlier reviews of the same task and a short profile of the student, so feedback can refer to what was said before.

**Code execution.** The sandbox is a subprocess in a temporary directory with CPU, memory, process-count and file-size limits, a scrubbed environment and a timeout. It is not container isolation. Running student tests is off by default and cannot be switched on in a production environment. Static analysis and compilation always run, for Python and JavaScript. A missing Node.js makes the JavaScript check fail rather than pass.

## The learning trajectory

An earlier version of this was a hand-weighted formula over four numbers. It could say that a student was doing poorly, but not at what. I replaced it with a model of individual skills.

```mermaid
flowchart LR
    S["Reviewed submissions<br/>criteria, objections, score"] --> E["Evidence<br/>criterion to skill, with a weight"]
    E --> B["Bayesian knowledge tracing<br/>forgetting, partial credit,<br/>per-student prior"]
    B --> P["Planner"]
    P --> F["Focus skill<br/>and three concrete steps"]
    P --> N["Next task<br/>from the board"]
    P --> A["Board action<br/>revise, chat, close, next sprint"]
    P --> Q["Whom to ask,<br/>and a ready question"]
```

**Skills and evidence.** There are 14 skills (edge cases, validation, error handling, testing, algorithms, data structures, API design, storage, concurrency, security, and so on). A deterministic classifier assigns each criterion text to one or two of them. Every criterion in a review is one pass/fail observation. Objections from the adversarial reviewer count as weaker negative evidence, weighted by severity. The final score is used only when a review has no criteria.

**The model.** Each skill has a probability `P` that the student knows it. One submission updates it in three steps:

```
1. forget   P <- P0 + (P - P0) * 2^(-dt / h)      h doubles after a success on a different day,
                                                  halves after a failure
2. observe  Bayes update over all observations of the submission,
            each weighted by its reliability (a tempered likelihood)
3. learn    P <- P + (1 - P) * T                  once per submission, not once per criterion
```

The prior `P0` for a skill the student has not met yet comes from how they did on other skills, so a strong student does not start every new skill at the population mean.

**Parameters without data.** I have no logs of real students, so I did not fit `(P0, T, slip, guess)`. I wrote seven behavioural requirements instead. Examples: one clean submission must already predict a pass, two in a row must not count as mastery, three in a row must, and a failure after three successes should be read as a slip rather than a gap. A grid search then picked the values with the largest smallest margin across all seven: `(0.30, 0.30, 0.05, 0.30)`. The readiness threshold is not tuned either. The review scale gives `score = 1 + round(9 * pass rate)`, so a score of 8 needs a pass rate of 0.722, and that is the bar.

**What it decides.** It separates a gap from a slip by computing `P(knows | failed)`. A gap sends the student to the right teammate with a ready-made question; a slip means "check your code again". It picks a focus skill in a fixed order: unmet criteria of the current task, then a skill that is fading, then the skill where one more task gains the most, then something harder. The next task from the board maximises the expected realised gain, `(1 - P) * T * P_success`. This is the zone of proximal development written as a formula, without an extra tuning constant.

**Evidence, and how far it goes.** I generated 200 synthetic students over 24 tasks each, 10 seeds. The generator is an Additive Factors Model with forgetting, so it is deliberately not the model being tested. The task is to predict each criterion before it is graded.

| Predictor | AUC | Log loss |
|---|---|---|
| The earlier hand-weighted formula | 0.643 ± 0.017 | 0.709 ± 0.024 |
| Success rate of the whole student | 0.663 ± 0.013 | 0.638 ± 0.027 |
| Success rate per skill | 0.685 ± 0.024 | 0.629 ± 0.021 |
| BKT without forgetting | 0.687 ± 0.015 | 0.651 ± 0.031 |
| **BKT with forgetting (this model)** | **0.689 ± 0.013** | **0.627 ± 0.027** |

It is clearly better than the formula it replaced and matches a strong per-skill baseline on prediction. The difference in what it can do shows up elsewhere. Asked to name the student's weakest skill, it is right 32% of the time, against 15% for a random pick and 13% for "the skill they failed last". Both results depend on the simulator's assumptions. They show the model behaves sensibly, not that it helps real students.

## The team chat

```mermaid
flowchart LR
    Q["Student message<br/>plus trajectory briefing"] --> R{"route"}
    R -->|"@mention, keywords,<br/>trajectory says 'ask'"| D["deterministic route"]
    R -->|"nothing matched"| L["LLM router, JSON output"]
    D --> MODE{"mode"}
    L --> MODE
    MODE -->|solo| SO["one teammate answers"]
    MODE -->|huddle| H["advisors write notes,<br/>the lead teammate answers"]
    SO --> PE["process_eval"]
    H --> PE
    PE --> FIN["finalize<br/>transcript, episode memory"]
```

Sara (product), Mike (analytics), Emma (QA) and John (tech lead) each have a persona and a focus area. Emma retrieves from the bug-pattern notes, the others from the best-practice notes. A message that touches two areas becomes a huddle led by John. When the trajectory says the student should talk something through, the reply comes from the teammate who owns the weak skill (unless the student names someone else), and the input box is prefilled with a ready question. The router prefers cheap deterministic rules, and the LLM is the fallback.

## The career layer

| Grade | Salary (simulated, RUB) | What changes |
|---|---|---|
| Intern | 70,000 | One teammate per chat turn. Acceptance criteria are shown after the first submission |
| Junior | 110,000 | The brief as written |
| Junior+ | 150,000 | Criteria are visible up front. The student picks which task to start. A peer-review task appears |
| Strong | 190,000 | The brief loses its step-by-step plan. One appeal per sprint |
| Offer | 240,000 | As Strong, and the student chooses the next project's direction and can reopen old letters |

What is shown by grade is decided in the client (`frontend/src/lib/career-rights.ts`), not enforced by the API.

- **Sprint end.** When the tasks are done, the student gives a Friday demo (a two to four sentence pitch and one question). Then a letter arrives from the tech lead. It is a promotion (next grade, plus a bonus of 20% of the new salary, halved if the pitch was weak), no raise (most tasks were closed weakly), or a freeze (the trajectory is thin). A thin trajectory freezes the raise; it does not block the next sprint. If the trajectory service cannot be reached, completion is held.
- **Bonus.** It can be spent during the next sprint on an extra review round, a one-turn session with Emma, or criteria before submitting. Whatever is left is replaced by the bonus in the next letter.
- **Night incident.** An optional task that arrives as a message from Emma: production is returning 500. A full pass adds a one-off bonus to the letter.
- **Peer review.** From Junior+, the student reads a snippet generated by the LLM with one planted bug and writes down what is wrong. The generator is checked so the bug text does not leak into the code, and a fixed snippet is used if generation fails.

## Memory

| What | Where | Access |
|---|---|---|
| Best practices, bug patterns | ChromaDB, semantic layer, from Markdown files in `agent_service/app/infrastructure/knowledge` | Vector search |
| Past reviews, chat episodes | ChromaDB, episodic layer, with age limits and recency weighting | Vector search, scoped by user |
| **Student profile** | MongoDB, one document per student, at most two typical problems | Direct read by `user_id` |
| Chat transcripts | MongoDB, thread per user and task | Direct read |
| Review and chat run state | Redis (LangGraph checkpoints, with a TTL) | By thread id |
| Retrieval cache | Redis | By query |

The student profile used to live in the vector store. It is a single short record per person, so similarity search added nothing: the record was either found or silently missing when its embedding did not rank. Now it is fetched by key. Writes to memory follow the same rules everywhere: text is compressed, empty or filler text and pasted solutions are rejected, and personal records need a user id.

## Testing and evaluation

- **243 unit tests** (`submission_service` 47, `task_service` 90, `agent_service` 106). They cover the scorecard and its caps, the close gate, the knowledge model, the planner, memory rules, checkpoint round trips, routing and the career rules.
- **Offline eval harness** in [`agent_service/evals`](agent_service/evals). It runs the deterministic part of the pipeline (tools, rubric, caps) with no LLM and checks the expected caps, and can run a small set of LLM-backed review and chat cases against a running stack. The dataset is small: 5 review cases and 5 chat cases. It is a regression net.
- **Simulation** of the trajectory model, as above: `python -m submission_service.app.application.trajectory.simulation`.
- **Load scenario** for the gateway in [`tests/locust`](tests/locust). I have no results to publish.

## Observability and deployment

- **Telemetry.** Services export OpenTelemetry traces to Tempo, logs go through Promtail to Loki, metrics go to Prometheus with Alertmanager, and Grafana ships with provisioned dashboards. Each graph node is a span. LLM calls can be traced in Langfuse (off by default).
- **Compose.** `docker-compose.yml` starts the services, the client, Kafka and the observability stack.
- **Kubernetes.** Helm charts for each service and an umbrella chart (`charts/`). Argo CD applications, Istio, Cilium, an HAProxy and Keepalived edge, external-secrets against Vault, and kube-prometheus-stack are described under `gitops/`. Terraform bootstraps namespaces and base secrets (`infra/`), and an Ansible role installs Kafka with Strimzi (`ansible/`).
- **CI.** A GitHub Actions workflow on a self-hosted runner builds the images with Kaniko, commits the new image tag to the Helm values, and triggers an Argo CD sync when credentials are configured.

These are deployment definitions. I have not run them at scale.

## Running it

You need Docker, a MongoDB and a Redis reachable from the containers (the compose file does not start them), and an API key for an OpenAI-compatible endpoint.

```bash
cp docs/.env.example .env      # fill in hosts, secrets and the LLM settings
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:3000 | Client |
| http://localhost:8005 | API gateway |
| http://localhost:3001 | Grafana |
| http://localhost:4000 | Langfuse |

The repository ships the platform, not a curriculum. There is no seed data, so before the first login:

1. Register a user in the client.
2. In MongoDB, insert `{ "user_id": <your id>, "role": "superadmin" }` into the `admins` collection of the user database. There is no bootstrap command for this yet.
3. Open the admin panel and create a project template. Sprints are entered as JSON; the panel starts with an example.

**Tests.** The services read their settings when the code is imported, so the environment must be filled in even for unit tests. They do not connect to anything, so any values will do:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r submission_service/requirements.txt -r task_service/requirements.txt \
            -r agent_service/requirements.txt pytest

set -a; source <(sed -E 's/=$/=1/' docs/.env.example); TASK_SERVICE_REDIS_PASSWORD=1; set +a
pytest submission_service/tests task_service/tests agent_service/tests
```

Python 3.12 is what the images use.

## Limitations

- **No study with real students.** I do not know whether this improves learning. The trajectory results come from simulation, and their assumptions are the simulator's.
- **The skill map is rule-based.** Criteria are assigned to skills by keyword patterns in Russian and English. Nobody has validated them against human labels, and a wrong assignment feeds straight into the knowledge model.
- **The parameters are derived, not fitted.** With real logs they should be estimated (EM, or a grid search on likelihood), and the seven constraints are a good sanity check for the result.
- **LLM grades vary.** The caps make scores more predictable, not more valid. I have not measured agreement between the pipeline and human graders.
- **The sandbox is process-level.** It is fine for a prototype and would need containers before untrusted use.
- **Language and scope.** Prompts, personas and the interface are in Russian. Static analysis covers Python and JavaScript only.
- **Little content.** No task corpus, and the eval dataset is small. The first superadmin is created by hand.
- **Grade-dependent hints are client-side.** A determined student can see everything through the API.

Things I would do next, in order: collect real submission logs from a small cohort, label a sample of criteria to measure the skill classifier and the reviewer against humans, fit the model parameters, and compare the trajectory against a fixed task order in a classroom trial.

## Where to start reading

| File | What is in it |
|---|---|
| [`review/scorecard.py`](agent_service/app/application/review/scorecard.py) | How the score and the caps are composed |
| [`graphs/review_graph.py`](agent_service/app/application/graphs/review_graph.py) | The review pipeline as a LangGraph |
| [`review/agent_path.py`](agent_service/app/application/review/agent_path.py) | The process checks on the agents |
| [`trajectory/knowledge.py`](submission_service/app/application/trajectory/knowledge.py) | The knowledge model: forgetting, evidence, per-student prior |
| [`trajectory/planner.py`](submission_service/app/application/trajectory/planner.py) | Focus skill, plan, and choice of the next task |
| [`trajectory/calibration.py`](submission_service/app/application/trajectory/calibration.py), [`simulation.py`](submission_service/app/application/trajectory/simulation.py) | Where the parameters and the numbers above come from |
| [`career.py`](task_service/app/application/career.py) | Grades, letters, bonus and their rules |

## Repository map

```
api_gateway/          reverse proxy, rate limiting
user_service/         accounts and roles
task_service/         projects, sprints, board, career rules
submission_service/   submissions, review loop, learning trajectory
  app/application/trajectory/   skills, evidence, knowledge model, planner, calibration, simulation
agent_service/        review graph, team chat, memory, evals
  app/application/review/       rubric, scorecard, adversarial check, process check
  app/application/graphs/       LangGraph definitions
  evals/                        offline evaluation
frontend/             React client
charts/ gitops/ infra/ ansible/   deployment definitions
monitoring/ monitoring_python/    telemetry configuration and FastAPI instrumentation
docs/                 trajectory model write-up, env template, images
```

## Author

Alexandra Kalimullina, [@alexaaa-a](https://github.com/alexaaa-a).
