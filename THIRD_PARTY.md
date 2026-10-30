# 外部ライブラリと出典

このリポジトリ自身のコードは [0BSD](LICENSE) で提供します。Cargoで取得する外部ライブラリ、公式の問題文・入力・採点ツールには、それぞれの配布元の条件が適用されます。このリポジトリのライセンスで置き換えるものではありません。

外部crateのソースや公式ツールは、このリポジトリには同梱していません。`Cargo.lock` は依存先と版の記録です。

2026-10-30に、ロックされた依存パッケージのCargoメタデータで確認したライセンスは次の通りです。

| パッケージ | 版 | 宣言されたライセンス |
|---|---|---|
| ac-library-rs | 0.2.0 | CC0-1.0 |
| autocfg | 1.5.1 | Apache-2.0 OR MIT |
| either | 1.15.0 | MIT OR Apache-2.0 |
| itertools | 0.14.0 | MIT OR Apache-2.0 |
| num-integer | 0.1.46 | MIT OR Apache-2.0 |
| num-traits | 0.2.19 | MIT OR Apache-2.0 |
| proconio | 0.5.0 | MIT OR Apache-2.0 |
| rustc-hash | 2.1.1 | Apache-2.0 OR MIT |
| superslice | 1.0.0 | Apache-2.0 |

依存の更新時は `cargo metadata --locked --format-version 1` と各配布元のライセンスを確認してください。依存コードやそれを含む実行ファイルを再配布する場合は、該当する条件を別途確認してください。

AHC LabのWindowsでのプロセス管理は [MicrosoftのJob Objectsの仕様](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) に基づいて実装しています。Microsoftの実装コードを同梱したものではありません。

テンプレートの利用許諾と、コンテストの事前公開・出典表示のルールは別です。参加する大会のルールを確認してください。
