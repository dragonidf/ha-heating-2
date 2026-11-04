# WP2B design contract

Reference: approved `docs/spec/heating-ai-2.0/05-UI-design.md` and `ui-concept.svg`; no third-party branding or image brief. Home answers comfort, authority and next session; one alert; advanced details stay collapsed. Desktop7:5, tablet chart spans both columns, mobile one chart plus compact cycle/circulation; bottom navigation only on mobile.

| Semantic token | Dark | Light |
|---|---|---|
| canvas | #111318 | #F5F6F8 |
| surface | #1B1E26 | #FFFFFF |
| raised | #252A35 | #ECEFF4 |
| text | #F2F0EC | #20232B |
| muted | #ADB5C4 | #525E70 |
| border | #394150 | #CDD3DD |
| prediction | #B8AAFF | #6650BA |
| control | #8EDBD0 | #176F67 |
| heating | #FF8E8E | #AE333F |
| warning | #F4C872 | #8B5B0A |

CSS names are local demo variables; global HA themes are untouched. Graphite surfaces,4/8px spacing, cards20px/controls12px, semantic status text and dashed/dotted curve patterns. Controls use muted boundaries and44px minimum. Typography uses rem for genuine200% enlargement; critical flex/grid children wrap. Forecast/energy/cost use separate axes. Charts have scope labels, shared readout, a table, and textual event descriptions. Reduced motion removes transitions/animation.

Runtime font is the HA-like system stack; no font download. Screenshot-only DejaVu normalization avoids runner font substitutions without changing shipped UX. Automated WCAG AA checks run in real browsers; they do not replace screen-reader/owner-phone practical acceptance.
