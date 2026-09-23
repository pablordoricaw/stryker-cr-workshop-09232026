# docs/humans/

Participant-facing materials meant to be read by people (not agents or notebooks).

## Kickoff deck

[`kickoff-deck.html`](kickoff-deck.html) is the hands-on workshop kickoff slide
deck. It covers the three domains, the checkpoint map (what you build end to
end), how to fork/set up in your workspace, and the Genie Code hint ladder.

### Open it locally

The deck works fully offline; no build step and no internet. It is a single
HTML file with all CSS and JS inlined; its one local dependency is the workshop
architecture diagram at `assets/diagrams/workshop-architecture.svg`, referenced
by relative path. Keep the deck inside the repo (both `docs/humans/` and
`assets/` ship together) so that reference resolves. Just open it in a browser:

- **Double-click** `kickoff-deck.html` in your file browser, or
- Drag the file onto an open browser window, or
- From a terminal, open it with your OS default browser:

  ```bash
  # macOS
  open docs/humans/kickoff-deck.html
  # Linux
  xdg-open docs/humans/kickoff-deck.html
  # Windows
  start docs\humans\kickoff-deck.html
  ```

### Navigating the deck

- **Advance:** `→`, `Space`, `Page Down`, or the on-screen `→` button.
- **Back:** `←`, `Page Up`, or the on-screen `←` button.
- **Jump:** `Home` (first slide), `End` (last slide).
- **Touch:** swipe left/right on a tablet or phone.

A progress bar and a slide counter track where you are. The deck is responsive,
so it presents well on a projector and reads fine on a laptop or phone.
