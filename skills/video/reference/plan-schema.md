# plan.json schema

Source of truth: `src/loom/plan.py` (pydantic; unknown fields are rejected).

```json
{
  "title": "Adding a task in Taskboard",
  "slug": "taskboard-add-task",
  "goal": "Viewer can add a task",
  "audience": "New team members",
  "viewport": {"width": 1920, "height": 1080},
  "redact": [".api-key", "#user-email"],
  "approved": false,
  "scenes": [
    {
      "id": "01",
      "narration": "Hi! In this short video I'll show you how to add a task in Taskboard.",
      "actions": [{"type": "title", "heading": "Adding a task", "subheading": "Taskboard basics"}]
    },
    {
      "id": "02",
      "title": "Open the board",
      "narration": "Here's the board. Your existing tasks are listed right here.",
      "actions": [
        {"type": "goto", "url": "https://app.example.com/board"},
        {"type": "highlight", "selector": "#list"}
      ],
      "expect": {"selector_visible": "#list"}
    },
    {
      "id": "03",
      "narration": "Type the task into the box and click Add task. It shows up at the bottom of the list.",
      "actions": [
        {"type": "type", "selector": "#task", "text": "Record the deployment walkthrough"},
        {"type": "click", "selector": "role=button[name=\"Add task\"]"}
      ],
      "expect": {"text_visible": "Record the deployment walkthrough"}
    }
  ]
}
```

## Plan fields
| field | notes |
|---|---|
| `title`, `slug` | slug: lowercase, digits, `-`; also the folder name in the recordings directory |
| `redact` | CSS selectors blurred on every page for the whole recording |
| `approved` | must be `true` before `loom record` will run |
| `viewport` | default 1920×1080, matches the output video |

## Scene fields
| field | default | notes |
|---|---|---|
| `id` | — | unique; `[A-Za-z0-9_-]`; also names `narration/<id>.wav` |
| `narration` | — | exact text spoken *and* used for captions |
| `actions` | `[]` | run in order while the narration plays |
| `expect` | none | `selector_visible`, `text_visible`, `url_contains`; checked after the actions; failure aborts the recording |
| `lead_in_s` | 0.3 | pause before the first action |
| `pad_after_s` | 0.6 | hold after the narration ends |
| `min_duration_s` | 0 | minimum scene length |

The scene lasts `max(actions, narration + pad_after_s, min_duration_s)`.

## Actions
Every action also accepts `"destructive": true` and `"note": "…"`.

| type | fields | behaviour |
|---|---|---|
| `title` | `heading`, `subheading?` | full-screen title card |
| `goto` | `url` | navigate |
| `click` | `selector` | cursor glides to the element, clicks (ripple shown) |
| `type` | `selector`, `text` **or** `secret_env`, `delay_ms`=55, `clear`=true | clicks the field and types visibly |
| `press` | `key` (e.g. `Enter`, `Control+A`), `selector?` | keyboard press |
| `hover` | `selector`, `ms`=600 | glide and hover |
| `scroll` | `selector` **or** `y` (px), `ms`=900 | smooth scroll |
| `select` | `selector`, `value` | choose a `<select>` option |
| `wait` | `ms` | pause |
| `wait_for` | `selector?`, `url_contains?`, `timeout_ms`=15000 | wait for page state |
| `highlight` | `selector`, `ms`=1500 | spotlight box around an element |

Selectors are Playwright selectors: CSS (`#id`, `.class`, `[data-testid=x]`),
`role=button[name="Save"]`, `text=Sign in`, and chains like
`#nav >> text=Settings`.
