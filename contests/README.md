# 大会ごとの作業場所

リポジトリ直下から `python ahc-lab/new_contest.py <大会ID>` のように作成します。

```text
contests/<大会ID>/
  main.rs         編集・ビルドする単一のソース
  lab.json        この大会の設定
  open-lab.cmd    テスト画面の起動
  notes.md        自分の考察メモ
  inputs/         公式入力
  tools/          公式ツール
  runs/           自動テストの記録
  submissions/    連番保存した提出用ソース
```

この配下の各大会フォルダは既定でGitの対象外です。共通コードと大会中の作業を分け、未公開の解答や入力を公開用コミットへ含めない構成です。過去の作業場所は、新しい大会を作っても変更されません。
