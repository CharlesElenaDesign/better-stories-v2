# Better Stories. Built Faster. (v2.0)

Static HTML presentation for David Neilson's Titan Europe / New York sessions.

## Run locally

```bash
python3 -m http.server 8742
```

Then open http://localhost:8742/index.html

## v2.0 changes (Nov 2026)

- Main deck: em dashes removed, framework card imagery (`assets/cards/`), slide entrance animations, Resources QR block and Agents slide removed.
- Theming (`agentic-chapter/`): opens on a 6-tile picker (4 bid examples + 2 demo placeholders) with hover descriptions. Huw's slides are hidden (`class="huw-hidden"`, marked `data-huw-hidden`), not deleted.
- Example media lives in `assets/examples/` (see README.txt there). Only the Google butterfly video is in so far.
