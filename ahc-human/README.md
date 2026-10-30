# AHC用：空のmain・共通部品・構造の見本

問題ごとに構造を選べるよう、3つを分けています。Rustの標準ライブラリだけで動きます。

| 場所 | 役割 |
|---|---|
| [main.rs](main.rs) | 空の `fn main()`。解法・入出力・探索ループを決め打ちしない |
| [library.rs](library.rs) | 必要なものを選んでコピーする共通部品 |
| [examples/](examples/README.md) | 同じ小さな運搬問題を違う構造で書いた見本 |

## 部品一覧

| 部品 | 用途・注意点 |
|---|---|
| `Scanner` | 一括入力。`new` / `from_text` / `next`。対話型には使わない |
| `Timer` | 経過秒・時間の進捗・終了判定。限界時間には余裕を持たせる |
| `Rng` | SplitMix64、範囲内の整数、小数、シャッフル |
| `temperature` | 開始・終了温度間の幾何冷却 |
| `accept` | 山登り・焼きなましの受理判定。改善なら正のgainを渡す。Rngに依存 |

`library.rs` は部品を探しやすく1ファイルにまとめています。必要なstruct・impl・関数と、対応するuseだけをmain.rsにコピーします。Scannerは `std::io::{self, Read}`、Timerは `std::time::Instant` が必要です。探索のコードは自動では入りません。

最小化のgainは「旧評価−新評価」、最大化は「新評価−旧評価」です。温度は評価の差の大きさに合わせます。最良解は現在の解と別に保持します。固定seedで再現できるのは乱数列で、時間で打ち切る解答の結果まで同一になるとは限りません。

## 使う順番

1. 空のmain.rsから、問題固有の入出力と合法解を実装する。
2. 必要な共通部品だけコピーする。
3. 構造に迷ったら見本を参照し、完成計画の局所探索・パラメータ探索・ビームなどから、問題に合う構造を選ぶ。
4. 提出とAHC Labのため、最終的には単一のmain.rsにまとめる。

新しい大会は `python ahc-lab/new_contest.py <大会ID>` で作成します。作業先は `contests/<大会ID>/main.rs` になり、共通の部品・見本はそのまま使えます。

## 確認とテスト

作業フォルダ直下から：

```powershell
rustc --edition=2021 --test ahc-human/library.rs -o ahc-library-tests.exe
& ./ahc-library-tests.exe
```

見本の実行方法は [examples/README.md](examples/README.md)。10件／100件テスト・版の比較・提出用freezeは [AHC Lab](../ahc-lab/README.md) を使います。

## 出典と再利用

部品をコピーする場合は、公開した版のLICENSEと、参加する大会の公式ルールを確認してください。ソース内の出典URLは、コピーする部品に残します。開始前の版を特定したい場合はコミットSHAを含む固定リンクを使います。
