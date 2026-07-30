deh2decohack
============
Converts DeHackEd patches (.deh / .bex) AND ZDoom DECORATE lumps into
structured, human-readable DECOHack source targeting:

    patch format : dsdhacked
    feature set  : MBF21
    source port  : dsda-doom

Usage
-----
    python deh_parser.py input.deh [-o output.dh] [-f auto|deh|decorate]

or on Windows, drag a .deh or DECORATE file onto dehack2decohack.bat.

The input format is auto-detected: DeHackEd patches are recognized by their
version header / BEX section markers, DECORATE by `ACTOR <Name>` blocks.
Override with -f if a file fools the sniffer.

Can be run from ANY directory. deh_parser.py locates its sibling modules
(deco_emitter.py, deh_ir.py) and the data/ table folder relative to its own
location on disk -- not your current working directory -- so it behaves the
same whether you call it by relative path, absolute path, or drop the whole
folder next to your other Doom scripts. The .deh input path is resolved
relative to wherever you run it from, same as any normal command-line tool.
Output defaults to sitting next to the input file with a .dh extension.

Requires Python 3.8+. No third-party packages.

What it does
------------
- Overlays the DEH's deltas onto DECOHack's own base state table, then
  rebuilds labeled state blocks (spawn/see/missile/...) per thing and
  weapon by walking next-state chains, with letter-run compression
  (HEAD IJ 8), loop/wait/stop/goto idioms, Bright, Fast, and Offset.
- MBF pointers read misc1/misc2; MBF21 pointers read Args1-8. Args are
  rendered by type: fixed-point as decimals, sounds as "names", things
  as ids with name comments, and state args as labels where possible.
- Jump sub-chains reachable only through A_RandomJump / A_HealChase /
  A_JumpIf* state args are given synthesized labels (st1234:) inside
  their owner's states block.
- States whose index identity matters (shared between things, edits to
  vanilla states of undeclared things, cross-referenced by index) are
  PINNED: emitted as top-level `state N { }` / `state fill N { }` blocks
  and referenced via `state <label> N` / `goto N`.
- Bits -> `clear flags` + flag list, re-asserting MBF21 base defaults
  (clear flags wipes both sets). MBF21-only edits become +/- flag diffs.
- Sprite renames (old-style Text 4/4 or [SPRITES] NAME=NAME) are applied
  in re-emitted states and carried onto untouched base things via
  per-thing `reskin OLD to NEW` clauses.
- dsdhacked numeric [SPRITES]/[SOUNDS] entries resolve inline; DEHEXTRA
  sounds 500-699 render as fre000-fre199.
- strings / pars / misc / ammo blocks are translated; old-style long
  Text renames are matched to BEX mnemonics via the default string
  table where possible.
- Every thing/weapon referenced in generated output is named using
  DECOHack's OWN built-in slot mnemonics (MT_* / WP_*, from its
  constants/*.dh includes that `#include <dsdhacked>` provides), so the
  names in comments match what you can actually type in DECOHack. A name
  declared by the patch itself always takes precedence over the mnemonic.
- Pinned state blocks say who they belong to. If the patch declares the
  owning thing/weapon, it is named directly. If the patch only edits
  Frame blocks and never declares an owner (a states-only patch), the
  vanilla base tables are used to report which stock actor's states
  those are and which chain they sit in, e.g.
      // vanilla thing 22 (MT_CYBORG) missile states
      // vanilla weapon 8 (WP_SUPERSHOTGUN) flash states

DECORATE conversion
-------------------
DECORATE and DECOHack share the same "SPRT ABCD 4 Bright A_Foo(args)"
state idiom, so states mostly translate directly. Handled:
- ACTOR blocks, editor numbers, properties, flags, state labels
- Same-file inheritance (`ACTOR Child : Parent`) is FLATTENED, since
  DECOHack has no inheritance; child values override parent values
- The Monster / Projectile flag-combo keywords are expanded (marked
  approximate -- verify against your needs)
- Standard state labels are lowercased (DECOHack labels are
  case-sensitive: `see` overrides the real See chain, `See` would make
  an unrelated custom label). Custom labels keep their case.
- `####` / `----` sprite and frame carry-over is resolved to the actual
  previous sprite/frame
- Random(x,y) durations become their midpoint (DECOHack has no random
  duration), noted inline
- ZDoom pointer names that are exact renames are converted outright
  (A_NoBlocking -> A_Fall). ZDoom-only pointers with a close MBF21
  equivalent get the recommendation in their TODO (e.g. A_SetSolid ->
  A_AddFlags(SOLID, 0), A_Jump -> A_RandomJump with reversed args).
- Comments are split by whether they need action: `// note:` is
  informational (a rename that was applied, a #### carry-over that was
  resolved), `// TODO:` needs your attention.

The Monster / Projectile flag combos are NOT guessed. They were derived by
taking the vanilla monsters and projectiles whose DECORATE uses each combo,
subtracting the flags those definitions state explicitly, and intersecting
across all of them:
    MONSTER    = SOLID | SHOOTABLE | COUNTKILL
    PROJECTILE = MISSILE | NOGRAVITY | DROPOFF | NOBLOCKMAP

Testing
-------
test_decorate/stock_monsters.dec holds the wiki's DECORATE definitions for
stock Doom monsters, and test_decorate/verify_stock.py converts them and
diffs the result against the REAL vanilla thing table -- properties, the
resulting flag set, and every state in every chain (sprite, frame, tics,
bright, action pointer). Because these monsters already exist in Doom 2,
this is a genuine correctness check rather than an eyeball test.

    python test_decorate/verify_stock.py

Currently 165 comparisons across 5 monsters, 0 mismatches. Sounds are
excluded by design (ZDoom uses SNDINFO logical names like "caco/sight";
DEH addresses sound lumps by index). One divergence is documented rather
than hidden: vanilla Lost Souls carry no COUNTKILL and so do not add to a
map's monster total, while ZDoom's MONSTER combo grants it.

NOT translatable -- these become `// TODO:` comments carrying the
original text rather than a guess:
- Parent classes not defined in the same file (ZDoom's own class tree)
- ZDoom-only action pointers (A_CustomMissile, A_Jump, ...), checked
  against the real dsdhacked/MBF21 pointer set
- Damage types, scale, alpha, renderstyle, tag, obituary, and other
  properties with no DEH equivalent
- `goto Label+offset` and `goto Class::Label`
- Thing slots: DECORATE has no slot concept, so slots are auto-assigned
  from 5000 up and flagged for you to renumber into your project's map.
  A DECORATE editor number becomes `ednum`, which is a separate thing
  from the patch slot.

Notes
-----
- The output is functionally equivalent, not byte-identical: DECOHack
  reallocates non-pinned state indices when it compiles. That is safe in
  dsdhacked's unlimited state space.
- ALWAYS recompile the output with DECOHack and test in dsda-doom.
  Anything the converter wasn't sure about is listed as a comment in a
  "Converter warnings" section at the end of the file and/or inline
  TODO comments.
- The data/ folder holds base tables generated by build_tables.py from
  dsda-doom and DoomTools sources. Regenerate only if those upstreams
  change (requires the source files in src_ref/, not included here).

Files
-----
  deh_parser.py         CLI entry point -- run this one
  dehack2decohack.bat   Windows drag-and-drop wrapper
  deh_ir.py             DEH/BEX tokenizer -> intermediate representation
                         (imported by deco_emitter.py; not run directly)
  decorate_convert.py   DECORATE parser + emitter
  test_decorate/        ground-truth test corpus + verifier
  deco_emitter.py        IR + base tables -> DECOHack source
  build_tables.py        regenerates data/*.json from engine sources
  data/*.json             base state/sprite/sound/thing/pointer/flag tables

All .py files and the data/ folder must stay together in the same folder
(wherever that is) for imports and table loading to resolve.
