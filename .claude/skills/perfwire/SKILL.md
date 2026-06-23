---
name: perfwire
description: Plans and audits hand-soldered perfboard (universal board / protoboard) wiring together with a human. Generates perfwire board-state JSON from a netlist/schematic, runs solver.py to place/route/audit under physical and EE constraints, and audits the human's edits from the index.html drag editor against physical reality. Use for perfboard / protoboard / universal board / jumper wiring / solder bridge / wiring plan / netlist-to-board requests. ユニバーサル基板・穴あき基板・配線計画・はんだブリッジ・perfwire の依頼で使用。
---

# perfwire — AI×人間のユニバーサル基板配線計画

## 原則

1. **写真から穴位置を推測しない**。実機の位置は人間がエディタ（index.html）のドラッグで入力する。AIの担当は「計画・割付・監査」。
2. **銅線は部品と同じ穴に挿せない**。被覆線の端は「ターゲットの足に隣接する空き穴＋はんだブリッジ」。空きが無いときだけ足へ直付け（`direct: true`）。
3. 正しさの根拠は常に**状態JSON**（README のスキーマ参照）。エディタと solver.py は同じスキーマを読み書きする。

## 前提：バンドル物の在処（コマンドの前に必ず 1 回 PLUGIN_ROOT を確定）

perfwire を**プラグインとして install** した利用者では、`solver.py`・`tools/*.py`・`config.example.json`・`index.html` は `~/.claude/plugins/cache/…` の中にあり、**あなた（エージェント）の作業ディレクトリ（＝利用者のプロジェクト）には無い**。`$CLAUDE_PLUGIN_ROOT` は Bash の環境変数として渡らない（inline 置換専用）うえ、**Bash ツールはコマンド間でシェル変数を保持しない**。だから素の `solver.py` では動かない。

**最初に 1 回だけ次を実行し、出力された絶対パスを控える**（以後のコマンドの `<ROOT>` をその値＝末尾 `/` 込み、`<PY>` を表示された解釈系に置換する）:

```bash
PY=""; for c in python3 python py; do "$c" -c "import sys" >/dev/null 2>&1 && PY="$c" && break; done   # Windows の python3 は「見つかりません」偽スタブのことがある→実際に動く物を選ぶ
ROOT=""   # 最新の installed 版を mtime 順で選ぶ（辞書順だと 0.10.0 < 0.6.0 になり旧版を掴む）。.in_use 付き(=使用中)を優先
for d in $(ls -dt "$HOME"/.claude/plugins/cache/*/perfwire/*/ 2>/dev/null); do [ -e "$d/.in_use" ] && [ -f "$d/solver.py" ] && ROOT="$d" && break; done
[ -n "$ROOT" ] || for d in $(ls -dt "$HOME"/.claude/plugins/cache/*/perfwire/*/ 2>/dev/null); do [ -f "$d/solver.py" ] && ROOT="$d" && break; done   # .in_use 無ければ最新 mtime
[ -f "${ROOT}solver.py" ] || { [ -f ./solver.py ] && ROOT="$(pwd)/"; }   # clone-and-open（cwd がリポジトリ）
[ -f "${ROOT}solver.py" ] || { ROOT=""; echo 'perfwire: プラグイン本体が見つかりません（~/.claude/plugins/cache/*/perfwire/*/ にも cwd にも solver.py なし）。install/更新を: /plugin marketplace update perfwire && /plugin install perfwire@perfwire' >&2; }
echo "PERFWIRE_ROOT=$ROOT"; echo "PERFWIRE_PY=$PY"
```

以後すべての solver / make_link / read_link 呼び出しは `<PY> "<ROOT>solver.py" …` のように**絶対パス**で行う（clone-and-open でも同手順でよい＝フォールバックで `<ROOT>` がリポジトリ root になる）。素の `solver.py` や `tools/…`（cwd 相対）は使わない。人にブラウザで開いてもらう `index.html` も `<ROOT>index.html` の絶対 file:// URL で渡す（§3。Windows は `/c/Users/…`→`file:///c:/Users/…` とドライブレター・`/` に）。**`PERFWIRE_ROOT` が空で返ったら**素の `solver.py` を実行せず（『solver.py が見つからない』の生エラーになる）、上のメッセージのとおり install/更新（`/plugin marketplace update perfwire`）を人に案内する。確定した `<ROOT>` は人にも一言添える（例「perfwire をプラグインキャッシュから使っています」）と空/誤 root に早く気づける。

## 連携パターン（誰がどう使うか — まず利用者タイプを見極める）

perfwire は Claude Code プラグイン。HTML はオフライン単一ファイル、solver.py は stdlib のみ。
**ネット・datasheet 調査・JSON 組み立て・監査はエージェント側**が担い、**穴位置の確定とはんだ作業は人間**が担う。
依頼者のタイプで入口と渡し方を変える（下の表が「全パターンを満たす」ための地図）。

| 利用者 | 入口の例 | エージェントの担当（この順で） |
|---|---|---|
| **初心者・会話のみ** | 「ブレッドボードのこの回路を基板に起こしたい」 | **JSON を一切見せない**。grid/部品/ネットを会話で聞き取り → state を組み立て → `--lint` → `--propose` → **`make_link.py` でディープリンクを生成して渡す**（裸の index.html や生 JSON を渡さない）→ `ee` を**平易な言葉**で要約（NG は「ここの線が長すぎるので隣の穴へ」と具体に）→ ブラウザの「作業ガイド」で1手順ずつ進めるよう案内（§3）。専門用語・配列ダンプは出さない |
| **ネットリスト/回路図持参** | 回路図・部品表・型番 | §1 で state 化。IC は `pinTypes`、外部入出力は `role` を datasheet から埋める（出力競合・電源ピン検査が有効化）→ §2 → §4 |
| **既存基板の記録（リバース）** | 実機写真 | §3 の**写真下絵**を案内（**人がトレース**、エージェントは写真から穴を読まない）→ 戻った JSON を §4 で監査 |
| **寸法・部品の根拠付け** | 「この抵抗/コンデンサの実寸を調べて」 | §5(a)。datasheet/代理店で調べ `physical.<kind>` の dims+`source` を **DEFCFG と config.example.json の両方**更新（`parity_check.mjs` が一致を CI 検証）。抵抗は電力定格(W)単位、電解は CV 単位で引く |
| **レイアウト調整** | 「斜めが多い／隣の穴に刺さって変／もっと整然と／組みやすく」 | まず**目的プリセット**（§2 の `--profile easy/analog/compact`）で意図を合わせる。さらに詰めるなら §5(b)(c)：craft 指標を**盤面自身の分布**から測り個別 `weights` を調整 → 再ソルブ → Pareto 実測。密基板の trade は魔法の重みで隠さず正直に提示 |
| **ブラウザ往復** | 人が編集して「書き出し」た JSON | §4。配線のみモードで再監査し `ee.fabReady` を総合判定として報告。案（proposals）は比較用に残す |

**渡し方の既定**: 監査が PASS したら**人間にはディープリンク（`make_link.py` の `index.html#z=…`）＋平易な要約**を渡すのが既定。生 JSON は中間生成物であって成果物ではない。
**config は単一・自動解決**: しきい値は `config.example.json` 一つ。solver は隣の `config.example.json` を `__file__` 基準で**自動解決**するので `--config` は省略可（絶対パスで叩く限り cache でも見つかる）。明示するのは調整版を渡すときだけ＝`--config "<ROOT>config.example.json"`。万一見つからなければ stderr に `EE audit DEGRADED` 警告（§2）。

## 往復ループ（人 ⇄ Claude Code）— これが本体。毎ターン「押す→戻す」をセットで指示する

初心者は1回の大往復でなく、**小さな往復を何度も**する：エージェントが「これを押して」と言う → 人が perfwire で押す → 結果を Claude Code に戻す → エージェントが確認して次の1手 → 繰り返し。**戻し方を毎回添えないとループが切れる**（初心者は書き出した後どうすればいいか分からない）。

**A. Claude Code → 人（指示）**: out.json を `make_link.py` でディープリンク化し、**1アクションずつ**指示する。「このリンクを開く → 赤くハイライトされた穴へ R5 をドラッグ → 『配線を再計算』を押す」。専門用語と JSON は出さない。`<PY> "<ROOT>tools/make_link.py" out.json --base "file:///<ROOT をドライブレター化>index.html" --task "R5 を赤い穴へドラッグして『配線を再計算』"`（make_link は絶対 file:// リンクを stdout に出す＝それを人に渡す）のように **`--task` を付けると、開いた瞬間に盤面上部の青い「Claude Code 連携」バーに『Claude からの指示』として表示**され、往復の3手順と **`Claude Code に戻す`** ボタンも同バーに出る（このバーは #z= リンク経由のときだけ出る＝ファイルを直接開く上級者には出ない）。初回 welcome は #z= 着信ではスキップされるので、このバーが CC 経由初心者の唯一の案内になる＝**指示は必ず `--task` に入れる**。

**B. 人 → Claude Code（戻し）— 指示の最後に必ず付ける**。盤面を戻す手段を初心者向け順に：
1. **`URL共有` ボタン**（最も簡単・1クリック1貼り付け）→ `#z=` リンクがクリップボードに入る → 「コピーされた URL をここに貼ってください」→ エージェントは `<PY> "<ROOT>tools/read_link.py" "<貼られたURL>" -o back.json` で復元（`read_link.py` は `make_link.py` の逆）。
2. **`書き出し` ボタン**（貼り付け不要）→ `perfwire_export.json` が **Downloads に保存**＋クリップボードにコピー → 「『書き出し』を押して『できた』と言ってください」→ エージェントは各 OS の Downloads（例 `~/Downloads/perfwire_export.json`）を読む。
3. クリップボードの JSON をそのまま貼る（`書き出し`/`コピー` が入れている）。

毎ターンの定型: 「○○を押して、終わったら **URL共有** を押し、コピーされたリンクをここに貼ってください」。戻ってきたら `<PY> "<ROOT>solver.py" back.json -o out.json`（配線のみ・config 自動解決）で再監査し `ee.fabReady` と差分を**平易に**報告 → 次の1手をまた指示。

**状態を戻さなくていい micro-loop**: 単純な確認（「監査パネルに『✓ 配線できた』が出ましたか？」「立て抵抗は何本？」）は**画面の平易な監査文言を読んでもらうだけ**で十分。毎回エクスポートさせない。盤面が変わったとき（配置/配線の編集）だけ B で戻す。

**よくある往復パターン**:
- *目的プリセット調整*: 「エディタ上部『配置の目的』で『組みやすさ』を選んで → URL共有 を貼って」→ エージェントが craft 指標で改善を実測 → 次案（§2 の `--profile`／§5(c)）。
- *つまずき診断*: 「押したけど何も起きない」→「URL共有 を貼ってください」で**状態を見てから**原因を言う（盤面が見えないまま推測しない。例: 部品が `locked` で動かない）。
- *ガイド付きはんだ*: `作業ガイド` を1手順ずつ。ここは状態でなく**画面の確認**でループ（「今の手順は何番？できたら次へ」）。
- *リバース記録*: 写真トレース（§3）→ `書き出し` → Downloads を読んで監査。

## ワークフロー

### 1. 新規プロジェクト（回路図/ネットリスト → 状態JSON）

ユーザーの回路から以下を組み立てて `<project>.json` を書く:

- `grid`: 実基板の穴数（ユーザーに確認）。ストリップ基板（ベロボード）は `grid.type:"strip"` ＋ `stripAxis:"row"|"col"`、`trackCuts:[[[c,r],[c2,r2]],…]` で銅箔ストリップとカットを表現（同一未カットストリップに異ネット＝`stripShorts` ＝ショート）
- `parts`: 各部品。kind は `ic`（pins辞書: DIP-8 はピン行間が3穴）/ `r` / `film` / `disc` / `elec`（plus=0 で leads[0] が＋極）。`leadNames` は `<id>.a/.b`（IC は `<id>.<pin>`）。動かせない部品は `locked: true`。任意 `family`（実部品名。例 `"Raspberry Pi Pico"` / `"リレー"` / `"インダクタ"`）で BOM・凡例の表示名を上書き（下記「対応部品とメタ拡張」）
- `leads`: 全リードの `{net, at}`。外部線は `W.` プレフィックスの単独リード。任意 `role` で電気的役割を宣言できる（`out`/`in`/`bidir`/`pwr`/`pwr_in`/`passive`/`oc`/`tri`/`nc`/`test`）。**外部の MCU 出力や電源が線で入ってくる端子は role を付ける**（例: `W.MCU_TX`→`role:"out"`、`W.RED`→`role:"pwr"`）。これにより基板外ドライバも出力競合検査の対象になる
- **基板の外へ出る接続（[client-hardware]スピーカー・マイク・電源など）の表現と可視化**: ①電源やMCU等は専用の外部端子 `W.<名前>` ＋ `role` で明示するのが最も分かりやすい（盤上に角タグ＋外向き矢印、凡例「外部接続」に表示）。②スピーカー/マイクのように**部品の足が直接外へ出る点**（例 SPK_P/SPK_N/MIC_IN が部品リードの単一リードネット）は、そのネットを `rules.single_lead_allowlist` に入れる＝I/O点として認識され、盤上に外向き矢印、凡例「外部接続」に**接続先を平易語で**（スピーカー（[client-hardware]）/マイク/電源 等、ネット名から推定）表示される。**[client-hardware]スピーカー線などは必ず allowlist に入れる**（入れないと単一リード＝結線漏れ警告になり、かつ外部接続として可視化されない）。よりリッチにしたいなら別途 `W.SPK_P` 等の外部端子＋wire で実体（はんだ点＋[client-hardware]への線）を表現してもよい
- `parts`（IC）: 任意 `pinTypes`（ピン番号→役割。例 opamp-ic: `{"1":"out","2":"in","3":"in","4":"pwr_in","5":"in","6":"in","7":"out","8":"pwr_in"}`）。**IC 生成時に datasheet から埋める**と出力競合・電源ピン検査が有効化される
- `netColors`: ネットごとの表示色
- `blockedHoles`: 物理的に使えない穴（ユーザーに確認）

#### 対応部品とメタ拡張（Raspberry Pi Pico・リレー・電磁部品など「個別未対応」の部品を loop で足す）

**`kind` は閉じた部品リストではなく、4つの幾何プリミティブ**（描画・配置・スパンの型）。**実際の部品名は `family` で付ける**。だから「個別にサポートされていない」部品も、正しいプリミティブで組み立てれば**コード変更なしで今すぐ載る**（描画・配線・ERC まで効く）。エージェントが datasheet/ピン配置を loop で調べて組み立てるのが担当。

| 実部品 | 使うプリミティブ | 組み立て方 |
|---|---|---|
| **Raspberry Pi Pico / MCUボード / モジュール** | `ic` | `pins` 辞書に実ピン配置（2×20=40本など、任意本数・任意座標）。`family:"Raspberry Pi Pico"`。`pinTypes` を datasheet から埋めると電源/出力検査も効く |
| **リレー・コネクタ・ピンヘッダ・トランジスタ・多ピン部品** | `ic` | 同上（名前付きピンの集合＝すべて `ic`）。`family` に実名 |
| **インダクタ・フェライトビーズ・無極性2リード** | `r` | 軸2リード（`leads`/`leadNames`）。`family:"インダクタ"` |
| **ブザー・有極2リード・電解** | `elec` | `plus` で極性。`family` に実名 |
| **フィルム/セラミック箱・円板** | `film`/`disc` | 既定の2リード箱/円板 |

例（Pico を載せる）: `{"id":"U3","kind":"ic","family":"Raspberry Pi Pico","label":"Pico","pins":{"1":[c,r],…,"40":[c,r]},"pinTypes":{…}}`。`ic` は**ピン群の外接矩形に箱を描く汎用多ピン部品**なので 40 ピンでもそのまま描画・配置・配線され、BOM/凡例は `family` で「Raspberry Pi Pico」と表示される（"IC" にならない）。

**loop での足し方**: ①ユーザーに型番/写真を聞く → ②エージェントが datasheet でピン配置・ピッチ・極性を調べる（オフライン境界＝§5(a) と同じ、ネット作業はエージェント側）→ ③上表のプリミティブ＋`family`＋`pins`/`leads` で組み立て → ④`make_link.py --task` で人に渡して実機どおりに配置してもらう → ⑤戻して監査。**新しい `kind` を増やす必要はない**。

**正直な限界（ここはコード変更が要る＝loop では足せない）**: perfwire は**スルーホール／名前付きピン or 軸リード**前提。①SMD（表面実装）パッド ②TO-220 のタブ等、ピンでも軸2リードでもない独自フットプリント ③その部品専用の固有グリフ — はプリミティブで近似できなければ index.html/solver.py の改修が要る。その場合は「プリミティブ近似で代用するか、コード対応するか」をユーザーに提示する。

### 2. ソルバー実行

```bash
# <PY> と <ROOT>（末尾 / 込み）は §前提 で確定した値に置換する。<project>.json/out.json は利用者 cwd の相対でよい（あなたが作る作業ファイル）。
<PY> "<ROOT>solver.py" <project>.json --lint                                               # 契約検証（生成直後に推奨）。クラッシュではなく構造化診断
<PY> "<ROOT>solver.py" <project>.json --propose --profile analog -o out.json               # 配置提案+配線+監査（目的=回路種別で選ぶ。下記）
<PY> "<ROOT>solver.py" <project>.json --config "<ROOT>config.example.json" -o out.json             # 配線のみ（配置は維持）
<PY> "<ROOT>solver.py" --list-profiles                                                     # 配置の目的プリセット一覧（easy/analog/compact）
<PY> "<ROOT>solver.py" <project>.json --emit-config -o my_config.json                      # 状態から config 叩き台を生成（要レビュー→ --config my_config.json で渡す）
<PY> "<ROOT>solver.py" <project>.json --propose-n --config "<ROOT>config.example.json"             # 重み格子で最良配置を探索
<PY> "<ROOT>solver.py" out.json --emit-packet -o build_packet.md                           # BOM＋切断長＋ブリッジのビルドパケット
<PY> "<ROOT>solver.py" out.json --guard INA_P --config "<ROOT>config.example.json" -o guarded.json # 高Zネットのガードリングを合成（案）
<PY> "<ROOT>solver.py" out.json --guard INA_P --guard-net SPK_OUT --config "<ROOT>config.example.json" -o guarded.json # ガード電位を明示指定
```

**生成した JSON は `--lint` で先に検証する**: 欠落キー・型不正・未知 kind・refdes 重複などの契約違反を、traceback ではなく人間可読な診断（error/warn）で返す。error があれば他のコマンドも実行前にクリーンに停止する。`--guard` 自動推定で候補が複数あると stderr に `ambiguous` 警告＋スコア付き候補一覧が出る（黙って先頭採用しない）＝ `--guard-net` で明示するか `config.guard_of` を設定する。`rail_volts`（V3V3/VMID/GND）は既定 config に同梱済みで、抵抗に `value`Ω があれば消費電力監査がそのまま効く。

**config は単一**: しきい値ファイルは `config.example.json` 一つに統一済み（旧 `perfwire_config.json` は廃止）。これは `--config` 無指定時の既定パスでもあり、solver が `__file__` 基準で自己解決するので `<PY> "<ROOT>solver.py" <project>.json` だけでも読み込まれる（cache でも cwd 非依存）。`--config <file>` を明示するのは調整版を渡すときだけ。万一 config が見つからなければ solver は内蔵 DEF_CFG にフォールバックし**デカップリング距離・配線長の監査が空**になる（スキルの中核機能が無効化）が、その際は stderr に `WARNING … EE audit DEGRADED` を必ず出す＝無言で無効化はしない。しきい値（部品寸法・ネットクラス・デカップリング近接・重み）を変えるときは `config.example.json` を直接編集するか、`--emit-config` の叩き台をレビューして `--config` で渡す。`config.example.json` の寸法・EE上限は `tools/parity_check.mjs` がエディタ内蔵 DEFCFG と一致を CI で保証する。
solver.py は標準ライブラリのみ（インストール不要）。出力の `stats` / `ee` / `warnings` を必ず確認し、NG はユーザーに報告する。

**配置の目的（手法プリセット）を回路種別で選ぶ** — 配置の良し悪しは単一の重みでなく**目的**で決まる。8本の生重みを平易な目的名に束ねたプリセットがあり、`--profile <key>` で適用する（人はエディタ上部の「配置の目的」ドロップダウンで同じものを選ぶ＝人とAIで語彙一致）。**エージェントは回路を見て目的を選ぶのが仕事**:

| プリセット | 何を優先 | こういう回路に |
|---|---|---|
| `easy`（組みやすさ・初心者おすすめ） | 直交・寝かせ・最小スパン・ゆとり間隔。手はんだと目視確認が最優先 | 汎用・学習用、依頼者が初心者、まず1枚組みたい |
| `analog`（アナログ・高感度） | 高Z入力を短く・入出力を強く分離・デカップリング近接 | オペアンプ/オーディオ/センサ/計装＝発振・ノイズに弱い回路（既定） |
| `compact`（省スペース） | ブリッジ多用で銅線最少・立て実装可・密でも可 | 小さい基板に詰める、上級者 |

目的は**「どう置くか」だけを変え、`ee`（fab-ready 判定）や EE 上限は不変**＝目的を変えても電気的合否基準は動かない。密な盤面では目的間に物理的 trade があり（例: easy は寝かせ優先で銅線が増える／compact はブリッジで銅線が減るが立てが増える）、**その trade を `--profile` で実測して正直に提示**する（§5(c)）。プリセット定義（重みベクトル＋名前）は `config.example.json` の `placement_profiles` と HTML 内蔵 DEFCFG が `parity_check.mjs` で一致保証。迷ったら `easy`、回路が感度系なら `analog`。

### 3. 人間の修正

`index.html` をブラウザで開いてもらう。install 利用者の cwd に index.html は無いので、`<target>` は §前提 の `<ROOT>index.html` を **file:// 絶対 URL** にしたもの（下記プリロードのディープリンク＝既定）。OS別: macOS `open <target>` / Linux `xdg-open <target>` / Windows PowerShell `Start-Process <target>`（cmd は `start "" <target>`）。

**盤面プリロード（推奨）**: `<target>` に裸の `index.html` ではなく、`<PY> "<ROOT>tools/make_link.py" out.json --base "file:///<ROOT をドライブレター化>index.html"` が出力する `file:///…/index.html#z=...` 絶対ディープリンクを渡すと、開いた瞬間に out.json の盤面が新規案として読み込まれる（既存の編集は保持＝非破壊）。Windows は `<ROOT>` の `/c/Users/…` を `file:///c:/Users/…`（ドライブレター・`/`）に。`make_link.py` は**フラット形状**（solver の out.json／エディタの「書き出し」）専用。`examples/client-hardware_tap_buffer.json` は `proposals[]` 形状なので渡せない。
プリロードしない場合は out.json を「開く…」かドラッグ&ドロップで読み込み。
ドラッグ修正 → 「書き出し」。エディタ内にも同じソルバーが内蔵されており、人間がスライダー＋再計算で自走できる。

**編集はモードレス直接操作**: 既定の「選択／移動」モードで、**部品も端子（銅線端・足）も同じ操作でそのままドラッグ**＝モード切替不要。クリック選択／**Shift＋クリックで複数選択**／空きをドラッグで範囲選択／選択をまとめてドラッグで移動。ロック/削除/選択解除は**盤上のアクションバー＋キー（L＝ロック切替・Del＝削除・Esc＝解除）**＝左パネルに戻らなくてよい。専門操作（ブリッジ/穴×/テスター/カット）だけ別モード。
- **ロックは人＋AI の「確定／未確定」シグナル**: エージェントは**確定済み（実機どおり/合意済み）の部品を `locked:true`** にして渡し、未確定は unlocked のまま残す。人はモードレスで未確定を並べ、気に入ったら **L でロック**、直したい所は外す。戻ってきたら `--propose` は**ロックを尊重**（locked と ic は動かさず、未ロックだけ再配置）＝人の意図を壊さず AI が続きを詰める。`locked` は状態JSONに乗り往復で保持される。

実機の記録（リバース）の場合は、**写真下絵**を案内する: 実機写真をエディタにドロップ →
不透明度/拡大/回転/左右反転（裏面写真）で穴を合わせる → 部品をなぞってドラッグ。
AI が写真から穴位置を読むのではなく、人間が写真をトレースするのが正しい分担。

### 4. 監査と確定

ユーザーから戻ってきた JSON を solver.py（配線のみモード）または独自チェックで監査:

- **ERC（はんだ前チェック）** — `ee` ブロックを必ず確認しユーザーに報告: `openNets`（未連結ネット）/ `unconnectedLeads`（ネット未割当の足）/ `duplicateIds`（refdes 重複）/ `multipleDrivers`（**出力-出力ショート＝ドライバ競合**。同一ネットに role=out が2本以上。基板外 MCU 出力端子も含む）/ `floatingPowerPins`（電源ピン浮き）/ `singleLeadNets`（単一リード=結線漏れ。`rules.single_lead_allowlist` で I/O 点は除外）/ `unclassifiedNets`（クラス未割当＝EEルール素通り）/ `polarity`（電解の逆極性。`rail_rank` 設定時に有効）/ `powerReach`（PWRネットが給電リードに到達。`power_entry` 設定時）/ `keepAway`（高Zノードの離隔違反）/ `decouplingCoverage`（電源ピンのバイパス存在）。`undrivenNets`（入力のみで駆動なし＝フローティング。passive バイアスは除外）/ `stripShorts`（ストリップ基板で異ネットが同一未カットストリップに同居）/ `resistorPower`（任意 `value`Ω＋`rail_volts` 設定時、P=ΔV²/R が定格超）/ `decouplingValueWarn`（バイパスに 1µF 超）/ `pinConflicts`（同一ネットに out と pwr＝出力を電源に短絡）。`ee.fabReady`（=eeNg 0 かつ非劣化）が総合ゲート。**`ee.degraded:true`（または solver の stderr に `DEGRADED`）なら config 未ロードで中核監査が空＝`fabReady` は信用しない。「PASS／はんだ付け OK」と人に言わず、まず config を直す**（§前提の絶対パス起動なら solver が config を自己解決するので通常は劣化しない）。`ee.fixes` に各指摘の機械可読な対処案が付く（advisory）。**出力競合・電源ピン・値考慮検査は `pinTypes`/`role`/`value`/`rail_volts` が宣言された場合のみ作動**（未宣言は誤検出回避でスキップ＝後方互換）
- 各ネットが連結か（union-find）/ 別ネットのパッドがブリッジされていないか
- デカップリング距離・クラス別配線長・本体重なり（tall×tall=NG）・パッド接合数
- **トポロジ/SI レビュー** — `ee.grounding`（スター/デイジーチェーン判定。リターンネットが daisy-chain なら共通インピーダンス結合の警告）/ `ee.guard`（高Zノードのガード助言）/ `ee.crosstalk`（平行近接の被覆線対。端点近似＝経路未モデルのため助言）
- PASS したら、はんだ作業はエディタの**作業ガイド**（1手順ずつハイライト・裏面ミラービュー・進捗保存）を案内する
- 実機検証はエディタの**導通リスト**ボタン（ネット別ビープアウト + ブリッジ厳禁ペアの markdown）と
  **テスターモード**（2穴クリックで計画上の導通判定）を案内する。独自チェックリストを別途生成してもよい

### 5. エージェント側の調査・批評（プラグインならではの人＋AIループ）

perfwire の HTML は意図的に**オフライン・単一ファイル**（実行時にネットへ出ない）。だからこそ、ネットや datasheet を要する作業は**エージェント（Claude Code）側が担い、結果を config／状態JSON／HTMLのDEFCFGに書き戻す**のが正しい分担。「実行時の自動検索」をブラウザに入れるのではなく、**ここで一度調べて出典付きで埋め込む**。

**(a) 部品の実寸を調べて寸法を根拠付ける（＝「自動検索」の正しい形）**
ユーザーの実部品（型番・秋月コード・電力定格）から、メーカー datasheet／代理店仕様で**本体寸法を調べ** `config.physical` を更新し、**出典を併記**する（HTML 側 DEFCFG／`PHYSREF` も同様に）。決定的な事実: **軸抵抗の寸法は電力定格＋系列で決まり、抵抗値では変わらない**（1MΩ も 10kΩ も同じ 1/4W なら同寸）＝per-値でなく**パッケージ（W）単位**で引く。電解は容量×電圧(CV)、フィルム箱は値/耐圧でピッチが決まるので**値依存で引く**。pinTypes と同じ「datasheet から埋める」流儀をリードにも広げる。
- 例: 「この基板の抵抗の実寸を調べて config を更新」→ 1/4W 炭素皮膜 ≈ 6.3–6.8×2.3–2.5mm（Yageo CFR-25／Vishay MRS25）等を反映＋出典コメント。
- 効果: `spans()` の有効スパン（寝=本体長から導出／立=1–2穴）が**実寸に基づき**、エディタ凡例に寸法＋有効スパン＋出典が表示される。

**(b) レイアウトの「職人目」批評（craft 品質）**
ERC/EE（電気）に加え**配置の craft 品質**を批評: 銅線長分布（HPWL）／斜め・過伸長の抵抗／立て実装の過多／交差・密集。閾値は固定値でなく**その盤面自身の分布**（中央比・再ソルブ下限）から導く（`span>5穴`のような決め打ちは禁止）。エディタ監査にも「レイアウト品質」行が出る。**立て抵抗は不具合でなく正当な垂直実装＝ERC エラーにしない**（隣接穴に刺さって見えるのは描画/可読性の話）。

**(c) よりクリーンな再配置（重み調整 → 再ソルブ → before/after 実測）**
craft 指摘の原因はソルバー目的関数の項の欠落。`config.weights` の `diag_penalty`（斜め抑制）/ `span_penalty`（伸長抑制）/ `standing_penalty`（立て抑制）を調整し `--propose` で再ソルブ、**同じ craft 指標を再測定**して「狙い軸が改善 ∧ 他軸を悪化させない（Pareto）」を実測確認する。**密な盤面では trade が物理的に避けられない**（斜めを消すと立てが増える等）＝正直に提示し魔法の重みで隠さない。HTML 内蔵ソルバーと solver.py は**同じ重みを一貫**更新する（parity は監査を比較＝配置目的の変更では破れない）。

## 注意

- 同値の抵抗は役割を入れ替えても電気的に等価。役割の同定は「ICのどのピンにブリッジ済みか」を最優先の証拠にする
- 案（proposals）は比較のために残し、採用案を明示する
- 状態JSONは git にコミットして履歴を残す運用を推奨
