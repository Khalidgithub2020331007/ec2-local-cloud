# Claude Instructions — Khalid's Projects

These rules apply to every task in every project. Follow them without being asked.

---

## Rule 1 — Consistency Check After Every Change

After making any code change, always verify it does not break consistency:

- **Naming:** New variables, functions, and files must follow the same naming convention already used in the project (camelCase, snake_case, kebab-case — match what exists).
- **Imports:** If a function is moved or renamed, find and update every file that imports or calls it.
- **Data shape:** If a data structure (object, type, DB schema) changes, update every place that reads or writes that shape.
- **Config:** If an env variable or config key is added, check that all environments (`.env`, `.env.example`, deployment configs) are updated too.
- **Before finishing a task**, run a quick grep to confirm nothing is left broken:
  ```bash
  grep -r "oldFunctionName\|oldVariableName" --include="*.ts" --include="*.js" --include="*.py" .
  ```
- If a change affects an API response shape, check the frontend that consumes it and vice versa.

**Never leave a partial change. Either fully apply it or don't apply it at all.**

---

## Rule 2 — Comments: 2-Line Max, Every Function and Every 5–10 Lines

Write comments that explain **WHY**, not **WHAT**. The code already says what it does.

### For every function:
```js
// Fetches paginated posts and caches the result to avoid repeated DB hits.
// Returns null if the user has no posts, caller must handle that case.
async function getUserPosts(userId, page) { ... }
```

### For every 5–10 lines of logic:
```js
// JWT has no expiry field by default — we add it manually at sign time.
const token = jwt.sign({ id: user.id, exp: ... });
```

### Rules for comments:
- Maximum **2 lines** per comment block — no paragraphs, no essays
- Never write: `// loop through users` or `// call the API` — these repeat the code
- DO write: hidden constraints, non-obvious reasons, workarounds, "why not the obvious approach"
- If a comment would say the same thing as the function name, skip it
- Use inline `//` for short notes, block `/* */` only if unavoidable

---

## Rule 3 — No Over-Engineering

Build exactly what is needed. Nothing more.

**Do not:**
- Add abstraction layers "for future use" — if there is no second use case right now, don't abstract
- Create base classes, factories, or registries unless there are 3+ concrete users of the pattern
- Add configuration options for behavior that only ever needs one value
- Write generic utilities when a specific 3-line solution works fine
- Add error handling for situations that cannot happen in this codebase
- Create helper files or utility modules unless the logic is reused in 2+ places

**Do:**
- Solve the problem directly in the simplest way that is still readable
- Prefer 10 lines of clear code over 30 lines of "flexible" code
- Ask: "will this abstraction be used in the next week?" — if unsure, skip it
- Three similar blocks of code is fine. Extract only at the fourth repetition.

**Test:** After writing code, ask — "could a junior developer understand this in 60 seconds?" If yes, it's the right level. If no, it's over-engineered.

---

## Rule 4 — UI: Clean, Consistent, and Usable

For any frontend or dashboard work:

**Layout:**
- Use consistent spacing — pick one spacing scale (4px, 8px, 16px, 24px, 32px) and never deviate
- Align elements on a grid — nothing should float randomly
- Group related things visually (forms, cards, table rows belong together)

**Typography:**
- One font family per project. Two at most (heading + body).
- Use 3 sizes maximum for body text: small (12–13px), normal (14–16px), large (18–20px)
- Headers should be clearly bigger than body text — no ambiguity about hierarchy

**Color:**
- One primary action color. One danger/error color. One neutral/text color.
- Backgrounds should be light and low-contrast — make the content stand out, not the background
- Every interactive element (button, link, input) must have a visible hover and focus state

**Feedback:**
- Loading states: always show a spinner or skeleton, never a blank space
- Empty states: always show a message like "No items yet" — never a blank table
- Errors: always show what went wrong and what the user can do about it
- Success: confirm actions that are not immediately obvious (e.g., "Saved" toast after form submit)

**Responsiveness:**
- Design for mobile-first if it's a public-facing page
- At minimum, ensure nothing overflows or breaks at 768px and 1280px widths

---

## Rule 5 — SRP: Single Responsibility Principle

Every function, file, and component must have exactly one reason to change.

**Functions:**
- A function does one thing. If you use "and" to describe what it does, split it.
  - ❌ `validateAndSaveUser()` → two responsibilities
  - ✅ `validateUser()` + `saveUser()`
- Functions should be short. If a function exceeds ~25–30 lines, ask if it should be split.

**Files / Modules:**
- One file = one concept. Examples:
  - `auth.service.ts` → only authentication logic
  - `user.controller.ts` → only HTTP request/response handling for users
  - `post.model.ts` → only the data shape and DB schema for posts
- If a file imports from 5+ unrelated modules, it is probably doing too much

**Components (Frontend):**
- A component renders one UI concept. A `UserCard` renders a card, nothing else.
- Data fetching and display are separate responsibilities:
  - Container component: fetches data, handles state
  - Presentational component: receives props, renders UI
- If a component has 3+ `useState` hooks for unrelated things, split it

**How to check SRP:**
> Complete this sentence: "This [function/file/component] is responsible for ___."
> If the blank needs more than one clause, split it.

---

## Rule 6 — Security: Never Trust, Always Validate

Security is not optional. Apply these on every task, not just "security tasks."

**Secrets and credentials:**
- Never hardcode passwords, API keys, tokens, or secrets in source code — not even in comments
- All secrets go in `.env` files. `.env` must be in `.gitignore`. Always.
- Always add a `.env.example` with dummy values so other developers know what variables are needed
- If you accidentally write a secret in code, flag it immediately to the user

**Input validation:**
- Validate ALL user input at the system boundary (API endpoints, form submissions, CLI args)
- Never trust client-sent data — always re-validate on the server even if the frontend validates too
- Sanitize inputs that go into SQL queries, shell commands, file paths, and HTML output
- Use parameterized queries / ORM methods — never concatenate user input into raw SQL

**Common vulnerabilities to always avoid:**
- **SQL Injection:** Use query parameters, never string interpolation in queries
- **XSS:** Escape HTML output, never use `dangerouslySetInnerHTML` with user content
- **Path traversal:** Never use user input directly in `fs.readFile`, `path.join`, or file serving
- **IDOR:** Always check that the logged-in user owns the resource they are requesting
  ```js
  // Always check ownership, never just fetch by ID
  const post = await Post.findOne({ id: postId, userId: currentUser.id });
  ```
- **Mass assignment:** Never pass raw `req.body` directly into a DB create/update — whitelist fields

**Authentication and authorization:**
- Check authentication before every protected route/action — not just at the middleware level
- Never expose stack traces, internal error messages, or DB errors to the client
- Tokens and session IDs must never appear in URLs (they get logged in server logs)

---

## Rule 7 — Error Handling: Explicit, Informative, Never Silent

Errors that are swallowed or ignored become production incidents.

**Never do this:**
```js
try {
  await doSomething();
} catch (e) {
  // silent catch — the worst pattern in existence
}
```

**Always do this:**
```js
// DB errors here are unrecoverable — rethrow so the global handler responds with 500.
try {
  await doSomething();
} catch (error) {
  logger.error('doSomething failed', { error, userId });
  throw error;
}
```

**Rules:**
- Every `catch` block must either: handle the error meaningfully, log it, or rethrow it — never all three and never none
- Errors shown to users must be human-readable: "Could not save your post. Please try again." — not "Error: SQLITE_CONSTRAINT"
- Errors logged internally must include context: what operation failed, what inputs were involved, what user triggered it
- Use a consistent error response shape across all API endpoints:
  ```json
  { "error": "NOT_FOUND", "message": "Post not found", "statusCode": 404 }
  ```
- Distinguish between operational errors (expected: user not found, validation failed) and programmer errors (unexpected: null reference, wrong type) — only catch operational errors in business logic

---

## Rule 8 — Naming: Clear Names Over Short Names

Good names eliminate the need for comments. Bad names require paragraphs to explain.

**Variables:**
- Name variables after what they contain, not their type: `userList` not `arr`, `isLoading` not `flag`
- Booleans must start with `is`, `has`, `can`, `should`: `isActive`, `hasPermission`, `canDelete`
- Avoid single-letter variables except in short loops (`i`, `j`) or math (`x`, `y`)
- Avoid generic names: `data`, `info`, `obj`, `temp`, `result`, `val`, `thing` — be specific

**Functions:**
- Functions that return a value: use a noun or noun phrase — `getUserById()`, `buildEmailTemplate()`
- Functions that perform an action: use a verb — `sendEmail()`, `deletePost()`, `validateInput()`
- Avoid misleading names: a function called `getUser` must not also send an email as a side effect

**Files and folders:**
- File name must match the primary export: `UserCard.tsx` exports `UserCard`, not `ProfileWidget`
- Folder names should be plural for collections: `components/`, `models/`, `routes/`, `utils/`
- Use consistent casing: `kebab-case` for files in most JS/TS projects, `PascalCase` for React components

**Avoid abbreviations** unless they are universally understood (`id`, `url`, `api`, `db`, `html`):
- ❌ `usrCnt`, `msg`, `btn`, `cfg`, `cb`
- ✅ `userCount`, `message`, `button`, `config`, `callback`

---

## Rule 9 — Database: Safe, Predictable, Non-Destructive

**Queries:**
- Always select only the columns you need — avoid `SELECT *` in production code
- Add indexes for every column used in `WHERE`, `JOIN`, or `ORDER BY` clauses on large tables
- Never run bulk deletes or updates without a `WHERE` clause — always scope the operation
- For soft-delete patterns, always filter `WHERE deleted_at IS NULL` — don't forget this filter

**Migrations:**
- Every schema change must go through a migration file — never alter the DB manually in production
- Migrations must be reversible (have a `down` method) where possible
- Never rename a column in a single migration if there is live traffic — add new column, migrate data, then drop old column
- Test migrations on a copy of production data before applying to production

**Data integrity:**
- Use database-level constraints (NOT NULL, UNIQUE, FOREIGN KEY) — don't rely only on application-level validation
- Wrap multi-step operations that must all succeed or all fail in a transaction:
  ```js
  // These two writes must both succeed or both fail — use a transaction.
  await db.transaction(async (trx) => {
    await trx('orders').insert(order);
    await trx('inventory').decrement('stock', 1).where('id', productId);
  });
  ```

**Sensitive data:**
- Never store plain-text passwords — always hash with bcrypt, argon2, or scrypt
- Never log full request bodies if they may contain passwords or payment data
- PII (name, email, phone) should not appear in application logs

---

## Rule 10 — API Design: Consistent, Predictable, Versioned

**HTTP conventions:**
- `GET` — read only, no side effects, safe to retry
- `POST` — create a new resource or trigger an action
- `PUT` — replace a resource entirely
- `PATCH` — update specific fields of a resource
- `DELETE` — remove a resource

**Response status codes — use the right one:**
| Status | When to use |
|--------|-------------|
| 200 | Success with response body |
| 201 | Resource created |
| 204 | Success with no response body |
| 400 | Client sent invalid data |
| 401 | Not authenticated (not logged in) |
| 403 | Authenticated but not authorized (no permission) |
| 404 | Resource not found |
| 409 | Conflict (duplicate, optimistic lock) |
| 422 | Validation error |
| 500 | Unexpected server error |

**Consistency rules:**
- All endpoints in a project must return the same response envelope shape
- All timestamps must be ISO 8601 format: `"2024-06-04T14:30:00Z"`
- All IDs must be the same type throughout (all strings or all numbers — never mixed)
- Paginated endpoints must always return: `data`, `total`, `page`, `limit`
- Never return a different shape for success vs error — always the same envelope, different fields populated

**Versioning:**
- Prefix all API routes with a version: `/api/v1/users` — not `/api/users`
- Never change the shape of an existing endpoint response — add a new version instead

---

## Rule 11 — Performance: Fast by Default

Don't optimize prematurely, but don't write obviously slow code either.

**Database:**
- Never query inside a loop — this is an N+1 problem:
  ```js
  // BAD: runs 1 query per post
  for (const post of posts) {
    post.author = await User.find(post.userId);
  }

  // GOOD: one query for all authors
  const authorIds = posts.map(p => p.userId);
  const authors = await User.findMany({ id: { in: authorIds } });
  ```
- Use pagination for any list that can grow: `LIMIT` + `OFFSET` or cursor-based
- Use `COUNT` queries sparingly on large tables — they are slow

**Frontend:**
- Never fetch data you don't display
- Debounce search inputs — don't fire a request on every keystroke
- Images must have explicit `width` and `height` to prevent layout shift
- Avoid re-rendering entire lists — use keys properly in React/Vue

**General:**
- Cache results that are expensive to compute and rarely change
- Avoid synchronous operations that block the event loop (Node.js: `readFileSync`, `execSync`)
- If an operation takes more than 2 seconds, it needs a loading indicator

---

## Rule 12 — Git and Version Control

**Before making changes:**
- Read the existing code in the area you're changing before editing anything
- Understand why the code was written the way it was before replacing it

**Commit discipline:**
- One commit = one logical change. Don't mix a bug fix and a refactor in the same commit.
- Commit messages must say WHY, not just WHAT:
  - ❌ `"fix bug"` `"update code"` `"changes"`
  - ✅ `"fix: prevent double-submit on payment form"` `"feat: add email verification on signup"`
- Follow Conventional Commits format: `type(scope): description`
  - Types: `feat`, `fix`, `refactor`, `style`, `docs`, `test`, `chore`

**What never goes into git:**
- `.env` files with real secrets
- `node_modules/`, `__pycache__/`, `.venv/`, build output folders
- Editor config files (`.vscode/`, `.idea/`) unless the project explicitly tracks them
- Log files, uploaded files, generated files

**Branch safety:**
- Never force-push to `main` or `master`
- Never commit directly to `main` in a shared repo — use a branch + PR
- Before pushing, always run `git diff` to review exactly what you're sending

---

## Rule 13 — File and Folder Structure

Keep structure predictable. A new developer should find any file within 30 seconds.

**General rules:**
- Group files by feature/domain, not by type, in large projects:
  ```
  ✅ features/auth/auth.controller.ts
     features/auth/auth.service.ts
     features/auth/auth.model.ts

  ❌ controllers/auth.ts
     services/auth.ts
     models/auth.ts
  ```
- In small projects (under 10 files per type), grouping by type is fine
- Never nest folders more than 3 levels deep unless absolutely necessary
- If a folder has only one file in it, it probably shouldn't be a folder

**File length:**
- If a file exceeds 300 lines, ask whether it is doing too many things
- If a file exceeds 500 lines, it must be split — no exceptions
- A single function should rarely exceed 30 lines

**Shared code:**
- Code shared between frontend and backend goes in a `shared/` or `common/` folder
- Never copy-paste logic between files — extract it once and import it

---

## Rule 14 — Communication and Responses

How Claude should behave when talking to Khalid.

**Before writing code:**
- If the task is ambiguous (could be solved in 2+ very different ways), ask one focused question before starting — don't guess wrong and do a lot of work in the wrong direction
- If the task is clear, just do it — don't ask for permission to start

**While working:**
- Give a one-sentence update when something unexpected is found: "The function doesn't exist yet — creating it now."
- If a blocker is hit, say what it is and what options are available — don't silently stop

**After finishing:**
- End with one or two sentences: what changed, and what (if anything) needs attention next
- Don't write a paragraph summarizing everything that was done — Khalid can read the code
- If the change has a side effect or trade-off worth knowing, mention it in one line

**When something is unclear in the existing code:**
- Say so: "This function looks like it may be unused — should I keep it?"
- Don't silently delete things that look wrong
- Don't silently add things that weren't asked for

**Tone:**
- Direct and concise — no filler phrases like "Certainly!", "Great question!", "Of course!"
- No emojis unless explicitly asked
- Treat Khalid as a capable developer — explain the WHY, not the basics

---

## General Behavior

- **Read before editing.** Always read the file before making any changes to it.
- **Small, focused changes.** One logical change per task — don't bundle unrelated fixes.
- **Ask before deleting.** Never delete a file or function without confirming it is unused.
- **Match the existing style.** Don't reformat code that isn't being changed — it muddies diffs.
- **No TODOs left behind.** If something can't be done now, say so explicitly — don't leave `// TODO` in the code.
- **No magic numbers.** Extract numeric literals into named constants: `MAX_RETRY_COUNT = 3` not a bare `3`.
- **Fail loudly in development, gracefully in production.** During dev, throw errors and crash fast. In production, catch and recover with a useful response.
- **Dependency caution.** Don't add a new npm/pip package to solve a problem that can be solved in 5–10 lines of native code. Every dependency is a future security vulnerability and maintenance burden.
- **Never run destructive commands without asking.** `DROP TABLE`, `rm -rf`, `git reset --hard`, `DELETE FROM` without WHERE — always confirm with the user first.
- **Environment awareness.** Never run seeding, migration rollbacks, or test data scripts against a production database. Always check which environment you are operating in.
