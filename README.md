# AtCoder Rust Template

ABC用の基本設定と、今後のAHCで使い回す共通部品・コードの見本・ローカルテスト環境を置くリポジトリです。大会固有の解答とデータは共通テンプレートから分けます。

## AHCを始める

Python 3.10以上とRustのコンパイラを用意します。テスト画面はPython標準機能だけで動き、追加パッケージは不要です。公式の採点ツールは各大会のものを使います。

実機での確認環境はWindows・Python 3.14・Rust 1.98です。他環境での動作は未検証です。設定に書いたプログラムを実行するツールなので、自分で確認したコードと設定を使用してください。

リポジトリ直下から：

```powershell
$contest = Read-Host "大会ID"
python ahc-lab/new_contest.py $contest
```

`$contest` には参加する大会IDを指定します。Windowsでは `new-ahc.cmd <大会ID>` でも作成できます。次に `contests/<大会ID>/open-lab.cmd` を開きます。既存の作業場所は上書きしません。

1. `main.rs` に問題固有の処理を書く。共通部品は必要なものだけコピーする。
2. 公式入力を `inputs/`、公式ツールを `tools/` に置く。
3. `lab.json` に採点方向・入出力方式・採点コマンド・時間制限・分類項目を設定する。
4. 設定後に `ready` をtrueにし、1件→10件→100件と確認する。
5. 残したい版を「提出用に保存」。連番の保存版からもテストできる。

画面を使わない操作も可能です。

```powershell
python ahc-lab/lab.py run --config "contests/$contest/lab.json" --count 10
python ahc-lab/lab.py freeze --config "contests/$contest/lab.json" --label "提出候補"
python ahc-lab/lab.py run --config "contests/$contest/lab.json" --submission submission-001.rs --count 100
```

## 構成

```text
ahc-human/
  main.rs                 空の入口
  library.rs              入力・乱数・時間・受理判定
  examples/               同じ運搬問題を違う構造で書いた見本
ahc-lab/
  lab.py                  自動実行・比較・分類表示・freeze
  new_contest.py          新しい大会の作業場所を作成
  web/                    ローカル画面
  demo/                   AHCとは別の動作デモ
  configs/                デモと設定例
contests/
  README.md               作業場所の説明
  ahcXXX/                 大会ごとのコード・設定・入力・結果（Git対象外）
tests/                    共通ツールの自動テスト
src/                      ABC用の基本main
snippets/                 ABC等でも使う部品
```

新しい大会を作るたびに、共通ライブラリや画面をコピー・修正する必要はありません。大会別のフォルダに `main.rs`・`lab.json`・入力・ツール・テスト記録・提出用保存版がまとまります。各大会フォルダは既定でGit対象外です。公開用の同期も配布ファイルの一覧で管理し、入力・解答・スコアを一括コピーしません。

## 共通部品と見本

[AHC用テンプレート](ahc-human/README.md)は、空のmain、選んで使うライブラリ、構造の見本を分けています。パラメータ探索・完成計画の局所探索・ビームの構造を比較できます。単一ファイルへまとめたコードを提出・テストする運用です。

[AHC Lab](ahc-lab/README.md)では10件／100件テスト、同じ入力での版比較、パラメータ別グラフ、ログ確認、提出用の連番保存ができます。分類や採点は各大会の設定を使います。公式の相対スコアとローカルの生得点は区別します。

`ahc-lab.cmd` は動作デモを起動します。公式入力や公式採点ツールは同梱していません。参加する大会で配布されたものを別途用意します。


## 動作確認

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
rustc --edition=2021 --test ahc-human/library.rs -o ahc-library-tests.exe
./ahc-library-tests.exe
```

ABCの基本設定は既存の `Cargo.toml`、`src/main.rs`、`snippets/` に残しています。ABC側の確認は `cargo check` で行えます。

`snippets/dsu.rs` の自作Dsuをコピーする場合は、`src/main.rs` の `use ac_library::Dsu` と同名になるため、そのimportを外してください。

公開対象を変更したときは `release-files.json` の配布一覧を確認し、Gitリポジトリで次を実行してください。

```powershell
python scripts/check-release.py
```

配布一覧外のファイル、個人の絶対パスや代表的な秘密情報の候補、作業データの除外設定を検査します。全種類の秘密情報や不具合を検出する保証はなく、差分と履歴の目視確認も必要です。

## 公開と大会中の利用

このリポジトリ自身のコードは [0BSD](LICENSE) です。コピー・変更・再配布にライセンス文の添付を要求しない条件で利用できます。外部crateや公式ツールの条件は別で、[THIRD_PARTY.md](THIRD_PARTY.md) に整理しています。

事前にAIを使って作成したコードを含みます。参加する大会の[公式ルール](https://info.atcoder.jp/entry/long-ahc-llm-rules-ja)と公開状況を確認してください。ローカルへコピーしただけではWeb公開にはなりません。提出にコピーする部品の出典URLはソース内にも残します。

開始前の版を示す際は、コミットSHAを含む固定リンクを使うと対象のコードを特定できます。フォーク後に変更した部分はその版の出典を記載してください。ライセンスの許可と大会ルールへの適合は別です。このリポジトリの利用を主催者が承認したという意味ではありません。

公開用に入れるのは共通部品・見本・テスト環境です。各大会の解答・入力・提出版・メモ・結果を公開する場合は、共通テンプレートの公開とは別に判断してください。
