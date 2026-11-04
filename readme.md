# このアプリについて

S3から .webm のオーディオファイルを読み取り、speech to text と要約を行うアプリです。

実施の流れ

- 10秒ごとに、S3の {S3_BUCKET_NAM}/{S3_AUDIO_PREFIX} をポーリングする
- ファイル（webm形式）が存在していた場合、以下の処理を行う。

1. ファイルを{S3_BUCKET_NAM}/{S3PROCESSING_PREFIX}に移動する
1. webm ファイルを amazon transcribeを 使って speech to text し、テキストファイルを {もとのファイル名}.txt で保存する
1. 上記のテキストファイルを Bedrock の Claude Haiku を使って要約し、{もとのテキストファイル名}_summary.txt というファイル名で保存する
1. データベースの更新（後述）
1. １〜４の処理が完了したら、音声ファイル、テキストファイル、要約後のテキストファイルを{S3_BUCKET_NAM}/{S3PROCESSED_PREFIX} に修正する。

## データベースの更新について

もとの音声ファイルは、{ゲームID}_{通番}_で始まる以下のような形式をしています。
`9994699a_5_A_aruaru_0006e4ca_あいう〜_20261029_115102.webm`

上記の例の場合、9994699a および 5 が通番です。

更新対象のデータベースのスキーマは以下のとおりです。

```
game.talks (
	game_id varchar NOT NULL,
	topic_number int4 NOT NULL,
	speaker varchar NULL,
	speaker_team varchar NULL,
	genre varchar NULL,
	like_count int4 NULL,
	summary varchar NULL,
	start_timestamp timestamptz NULL,
	whole_text varchar NULL,
	CONSTRAINT talks_pkey PRIMARY KEY (game_id, topic_number)
);
```

game_id = ゲームID かつ および topic_number = 通番 のレコードがすでに存在しているので、そのレコードを updateする形で、
- whole_text に テキスト全文
- summary に要約
の内容を設定する。

## データベースの更新について

## DBおよびS3との接続

.env ファイルに設定するべき項目を、.env.example ファイルに示しています。

処理中は、具体的な接続情報等は、.envファイルから取得します。

# テスト用機能の実装

rollback_s3.py は、s3 のファイルを以下の要件で整理するための処理です。

以下のいずれかの引数を指定できます。

```
rollback_s3.py --processing
rollback_s3.py --processed
rollback_s3.py --all
```

## rollback_s3.py --processing の実行内容

- {S3_BUCKET_NAM}/{S3PROCESSING_PREFIX} のテキストファイルをすべて削除します。
- {S3_BUCKET_NAM}/{S3PROCESSING_PREFIX} の音声ファイル（拡張子が .txt 以外のファイル）をすべて、{S3_BUCKET_NAM}/{S3_AUDIO_PREFIX} に移動します。

## rollback_s3.py --processed の実行内容

- {S3_BUCKET_NAM}/{S3PROCESSED_PREFIX} のテキストファイルをすべて削除します。
- {S3_BUCKET_NAM}/{S3PROCESSED_PREFIX} の音声ファイル（拡張子が .txt 以外のファイル）をすべて、{S3_BUCKET_NAM}/{S3_AUDIO_PREFIX} に移動します。

## rollback_s3.py --all の実行内容

rollback_s3.py --processing　および　rollback_s3.py --processed の両方を実行します。

