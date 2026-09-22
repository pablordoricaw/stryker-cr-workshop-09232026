# solutions/

Gated reference solutions for all three domains — the top rung of the hint
ladder and the ground truth maintainer CI runs end-to-end.

**Participants:** reach for these only through Genie Code's graded hints. Peeking
here skips the learning; try the nudge → skeleton → checkpoint-solution ladder
first.

Layout (added by later tickets, one subtree per domain):

```
solutions/
├── finance/
├── security/
└── itsm/
```

The Finance solution for checkpoint `01_bronze_txn` implements both the
admin-enabled Lakebase CDF path and the no-admin Delta fallback. Later solution
notebooks are authored alongside each build-spine ticket and validated by
maintainer CI (#17). This directory ships on both `dev` and the participant
release.
