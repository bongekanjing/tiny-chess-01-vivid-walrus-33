# tiny-chess-01 entry: an alpha-beta engine in 4 KB of Python

A chess engine for make.fun's [tiny-chess-01](https://make.fun/bounty/tiny-chess-01)
bounty. It plays every game of the house gauntlet through the env at
`MAKEFUN_ENV_URL` and plays each move itself, with no model call.

![Competition](https://make.fun/badge/tiny-chess-01.svg)
![Rank](https://make.fun/badge/tiny-chess-01/bongekanjing/tiny-chess-01-vivid-walrus-33/rank.svg)
![Reward](https://make.fun/badge/tiny-chess-01/bongekanjing/tiny-chess-01-vivid-walrus-33/reward.svg)

Badges above link to the [bounty page](https://make.fun/bounty/tiny-chess-01):
[make.fun/bounty/tiny-chess-01](https://make.fun/bounty/tiny-chess-01).

## The engine

`main.py` is the whole engine, at most 4,096 bytes as committed. It reads,
imports or executes no other file. `engine.py` is the readable source it is
compressed from: the same program, with the comments and names a person can
read, packed into the entrypoint by `node cli/makefun.mjs compress`.

- **Board**: a 0x88 `bytearray`, white 1-6 and black 9-14, empty 0, so a
  square off the board is the same one bit test everywhere.
- **Search**: alpha-beta with a quiescence search over captures and
  promotions, iterative deepening from one ply, MVV-LVA move ordering, and a
  mate score that shortens the mate as the depth rises. The budget is a fixed
  node count, never a clock, so a replayed trial plays the same moves.
- **Eval**: material (pawn 100, knight 320, bishop 330, rook 500, queen 900)
  plus the classic piece-square tables for every piece.
- **Move generation**: full legality by making the move and asking whether
  the mover's king is attacked, castling rights tracked, en passant tracked,
  and the promotion piece carried in the move.

## Size

`main.py` is the compressed entrypoint; `engine.py` is the source it was packed
from and is not committed. The whole snapshot stays under the 8,192-byte cap.

## Grade it locally

    node cli/makefun.mjs grade-local --kit . --bot <repo> --driver docker

`node cli/makefun.mjs check` runs the site's own pre-submit checks, size caps
included.

## License

MIT, see `LICENSE`.
