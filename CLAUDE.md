# slack-issue-agent での作業ルール

設計は `docs/PROJECT.md`、セットアップ手順は `README.md` を参照。

## コミット前の機密情報チェック(必須)

このリポジトリは**公開リポジトリ**。ファイルを変更してユーザーにコミットを頼む前に、コミット対象の差分(`git diff` と `git diff --cached` の両方)に機密情報・個人情報が含まれていないか確認し、結果をユーザーに伝える。

確認するもの:

| 種類 | 例・パターン |
|---|---|
| Slack のトークン | `xoxb-`、`xoxp-` など |
| Slack の Signing Secret | 32 桁の 16 進数。`n8n/.env` の `SLACK_SIGNING_SECRET` の実際の値とも照合する |
| AWS のアクセスキー | `AKIA` + 16 文字 |
| GitHub のトークン | `github_pat_`、`ghp_` など |
| Langfuse の鍵 | `pk-lf-`、`sk-lf-` |
| メールアドレス | `xxx@yyy.zz` の形(n8n の書き出しには持ち主のメールアドレスが入りうる) |
| 環境ごとの値 | Quick Tunnel の URL(`trycloudflare.com`)、AWS のアカウント ID(12 桁の数字) |

- 値そのものを画面に出さない(照合は件数だけを表示する)
- 説明文の中の「secret」「token」などの単語は問題ない。値が入っていないかを見る
- 見つかった場合は、コミットを頼まずにユーザーに報告する

## その他

- コミット・push・PR・マージはユーザーが行う。こちらからはコミットしない
- インフラの apply は CI(main へのマージ)で行う
- n8n のワークフローは `just n8n-export` で `n8n/workflows/` に書き出す(持ち主の情報や pinData は書き出し時に取り除かれる)
