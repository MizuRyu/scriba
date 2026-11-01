---
name: mono
description: モノクロ・ミニマルなデザインシステム。shadcn/ui風。個人ツールの横展開用。
origin: Scriba (meeting transcription tool) — Pattern 05

colors:
  light:
    bg: "#ffffff"
    card: "#ffffff"
    border: "#e5e7eb"
    fg: "#111827"
    muted: "#6b7280"
    light: "#f9fafb"
    hover: "#f3f4f6"
    success: "#16a34a"
  dark:
    bg: "#09090b"
    card: "#111113"
    border: "#27272a"
    fg: "#fafafa"
    muted: "#a1a1aa"
    light: "#18181b"
    hover: "#1e1e21"
    success: "#22c55e"

typography:
  fontFamily:
    sans: "-apple-system, 'Inter', 'Helvetica Neue', 'Hiragino Sans', 'Yu Gothic', sans-serif"
    mono: "'SF Mono', 'Fira Code', 'Consolas', monospace"
  scale:
    hero: "1.5rem / 700 / -0.025em"
    title: "1.25rem / 600 / -0.025em"
    heading: "1.125rem / 600 / normal"
    section: "1rem / 600 / normal"
    body: "0.9375rem / 400 / normal"
    small: "0.875rem / 400 / normal"
    caption: "0.8125rem / 400 / normal"
    label: "0.6875rem / 400 / 0.05em"
    micro: "0.625rem / 400 / normal"
  lineHeight:
    tight: 1.3
    normal: 1.6
    reading: 1.9

spacing:
  unit: "0.25rem"
  section: "2.5rem"
  card: "1.25rem"
  gap: "1rem"

rounded:
  none: "0"
  sm: "0.25rem"
  md: "0.375rem"
  lg: "0.5rem"
  full: "9999px"

components:
  button:
    primary:
      bg: "var(--fg)"
      text: "var(--bg)"
      border: "var(--fg)"
      rounded: "md"
      padding: "0.5rem 1rem"
      fontSize: "small"
    ghost:
      bg: "transparent"
      text: "var(--muted)"
      border: "var(--border)"
      rounded: "md"
      padding: "0.25rem 0.625rem"
      fontSize: "caption"
      hoverText: "var(--fg)"
      hoverBorder: "var(--fg)"
  tab:
    inactive:
      text: "var(--muted)"
      borderBottom: "transparent"
    active:
      text: "var(--fg)"
      borderBottom: "var(--fg)"
      borderWidth: "1.5px"
    gap: "2rem"
    fontSize: "small"
  card:
    bg: "var(--card)"
    border: "var(--border)"
    rounded: "lg"
    padding: "1.25rem"
  listItem:
    padding: "1rem 0"
    borderBottom: "var(--border)"
    hoverBg: "var(--hover)"
    hoverRounded: "md"
  kpi:
    labelSize: "label"
    labelTransform: "uppercase"
    labelLetterSpacing: "0.05em"
    valueSize: "hero"
    valueWeight: 700
  table:
    fontSize: "caption"
    headerColor: "var(--muted)"
    headerWeight: 400
    cellPadding: "0.5rem 0.75rem"
    borderBottom: "var(--border)"
    hoverBg: "var(--hover)"
    numFont: "mono"
    numSize: "0.75rem"
  sparkline:
    height: "60px"
    barGap: "3px"
    barColor: "var(--fg)"
    barRadius: "1px"
    tooltipFontSize: "micro"
---

# mono Design Guide

個人ツール横展開用のモノクロ・ミニマルデザインシステム。shadcn/ui の思想をベースに、白黒2色 + muted だけで情報を整理する。色に頼らず、タイポグラフィと余白で階層を作る。

## Visual Theme & Atmosphere

静かで機能的。装飾を排し、コンテンツ自体を主役にする。

- 色は fg / muted / border の3段階で情報の重要度を表現する
- アクセントカラーは success（緑）のみ。ステータス表示専用
- 影・グラデーション・アイコン装飾は使わない
- テーマ切替はOS設定に追従し、手動トグルも提供する

## Color Palette & Roles

| 役割 | Light | Dark | 用途 |
|---|---|---|---|
| bg | #ffffff | #09090b | ページ背景 |
| card | #ffffff | #111113 | カード・パネル背景 |
| border | #e5e7eb | #27272a | 区切り線・カード枠 |
| fg | #111827 | #fafafa | 本文・見出し・アクティブ要素 |
| muted | #6b7280 | #a1a1aa | 補助テキスト・非アクティブタブ・ラベル |
| light | #f9fafb | #18181b | セクション背景・ストライプ |
| hover | #f3f4f6 | #1e1e21 | ホバー背景 |
| success | #16a34a | #22c55e | 録音中インジケータ等のステータス |

色を増やさない。新しい意味を伝えたいときは、既存の fg / muted / border の組み合わせと、font-weight / font-size の変化で対応する。

## Typography Rules

### フォントファミリー

```css
/* 本文 */
font-family: -apple-system, 'Inter', 'Helvetica Neue', 'Hiragino Sans', 'Yu Gothic', sans-serif;

/* コード・数値 */
font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
```

- macOS環境前提のため -apple-system を先頭に指定
- 日本語フォールバックとして Hiragino Sans → Yu Gothic の順
- 数値・ファイルパス・技術的な値にはモノスペースフォントを使う

### サイズ階層

| 名前 | サイズ | weight | letter-spacing | 用途 |
|---|---|---|---|---|
| hero | 1.5rem | 700 | -0.025em | KPI数値、ページタイトル |
| title | 1.25rem | 600 | -0.025em | アプリ名 |
| heading | 1.125rem | 600 | normal | セッション詳細タイトル |
| section | 1rem | 600 | normal | セクション見出し |
| body | 0.9375rem | 400 | normal | 本文テキスト（文字起こし等） |
| small | 0.875rem | 400 | normal | タブ、ナビゲーション |
| caption | 0.8125rem | 400 | normal | 補助テキスト、統計値 |
| label | 0.6875rem | 400 | 0.05em | KPIラベル、メタラベル（uppercase） |
| micro | 0.625rem | 400 | normal | ツールチップ、チャートラベル |

### line-height

| 用途 | line-height |
|---|---|
| 見出し・ラベル | 1.3 |
| 一般UI要素 | 1.6 |
| 長文テキスト（文字起こし本文） | 1.9 |

日本語の長文は line-height: 1.9 を守る。1.6 以下にすると可読性が大幅に落ちる。

### 禁則処理

```css
word-break: break-all;        /* 不使用。日本語が不自然に折り返される */
overflow-wrap: break-word;     /* 長いURLや英単語の折り返しに使用 */
text-align: left;             /* 常に左揃え。両端揃えは不使用 */
```

## Component Stylings

### Button

2種類のみ。

**Primary**: fg背景 + bg文字。ページ内に1つだけ目立たせるCTA用。
```css
background: var(--fg); color: var(--bg); border: 1px solid var(--fg);
border-radius: 0.375rem; padding: 0.5rem 1rem; font-size: 0.875rem;
```

**Ghost**: 透明背景 + muted文字 + border枠。テーマ切替やサブアクション用。
```css
background: transparent; color: var(--muted); border: 1px solid var(--border);
border-radius: 0.375rem; padding: 0.25rem 0.625rem; font-size: 0.8125rem;
```
```css
/* hover */
color: var(--fg); border-color: var(--fg);
```

### Tab / Navigation

下線スタイル。背景色ではなく border-bottom で active を示す。

```css
/* inactive */
color: var(--muted); border-bottom: 1.5px solid transparent;

/* active */
color: var(--fg); border-bottom: 1.5px solid var(--fg);
```

タブ間のgapは `2rem`。詰めすぎない。

### List Item

border-bottom で区切る。カード化しない。

```css
padding: 1rem 0; border-bottom: 1px solid var(--border);
```
```css
/* hover: 左右にネガティブマージンで広がる */
background: var(--hover); margin: 0 -0.75rem;
padding-left: 0.75rem; padding-right: 0.75rem;
border-radius: 0.375rem;
```

### KPI / Metric

ラベル + 値 の2段構成。ラベルは label サイズ + uppercase + letter-spacing。

```css
/* label */
font-size: 0.6875rem; color: var(--muted);
text-transform: uppercase; letter-spacing: 0.05em;

/* value */
font-size: 1.5rem; font-weight: 700;
```

4列グリッドで並べる。 `grid-template-columns: repeat(4, 1fr);`

### Table

ヘッダーは muted / weight 400。行ホバーに hover 背景。数値列は右揃え + モノスペース。

```css
th { color: var(--muted); font-weight: 400; }
td { padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
tr:hover td { background: var(--hover); }
.num { text-align: right; font-family: 'SF Mono', monospace; font-size: 0.75rem; }
```

### Sparkline / Bar Chart

fg色の細いバー。高さ60px。ホバーでツールチップ表示。

```css
height: 60px; gap: 3px;
.bar { background: var(--fg); border-radius: 1px; }
.bar:hover { opacity: 0.5; }
```

### Status Indicator

点滅する丸ドット。success色のみ使用。

```css
width: 8px; height: 8px; border-radius: 50%; background: var(--success);
animation: pulse 2s infinite;
```

## Layout Principles

### コンテナ

```css
max-width: 720px; margin: 0 auto; padding: 3rem 1.5rem;
```

720pxのナローレイアウト。テキスト中心のUIは広すぎると読みにくい。

### 余白の単位

基本単位は `0.25rem`（4px）。主な余白:

| 用途 | 値 |
|---|---|
| セクション間 | 2.5rem |
| カード内 | 1.25rem |
| 要素間（gap） | 1rem |
| テキスト行間 | 0.375rem - 0.5rem |
| ヘッダー → コンテンツ | 2.5rem |

### 情報密度

中程度。詰めすぎず、散らかさず。1画面に収まる量を基準にする。スクロールは許容するが、ファーストビューに主要アクションとステータスが見えること。

### 区切り

- セクション間: border-bottom（1px solid var(--border)）
- カード: 使わない方向。border-bottom のリスト表示を基本にする
- メタ情報行: border-top + border-bottom で挟む

## Depth & Elevation

影は使わない。奥行きは背景色の微差（bg → light → hover）で表現する。border は区切り専用で、浮いている感じは出さない。

## Do's and Don'ts

Do:
- fg / muted / border の3段階だけで情報の重要度を伝える
- 日本語本文には line-height: 1.9 を使い、読みやすさを確保する
- 数値・ファイルパスにはモノスペースフォントを使う
- ホバーは背景色の変化だけ。アニメーションは最小限（opacity transition 0.15s）
- テーマ切替はOS設定追従 + 手動トグル。localStorage で記憶する
- 1ページに primary ボタンは最大1つ
- テーブルの数値列は右揃え

Don't:
- 色でカテゴリ分けしない。モノクロで伝わらない情報設計は構造が間違っている
- box-shadow を使わない
- border-radius を lg (0.5rem) より大きくしない
- font-size を 0.625rem (micro) 未満にしない
- 日本語本文を line-height 1.6 未満で表示しない
- uppercase を日本語テキストに適用しない（ラベル英字のみ）
- グラデーション・ぼかし・半透明オーバーレイを使わない
- アイコンに頼って意味を伝えない。テキストラベルを基本にする

## Responsive Behavior

現時点ではデスクトップ（720px幅）のみ対象。

将来モバイル対応する場合:
- KPI 4列グリッド → 2列
- テーブル → カードリストに変換
- container padding を 1rem に縮小
- font-size はそのまま維持（0.875rem以上は十分読める）

## Agent Prompt Guide

このファイルを読んだAIエージェントがUIを実装する際の指針:

1. **最優先**: コンテンツの可読性。装飾より余白とフォントサイズに注力する
2. **色の判断**: fg（重要）→ muted（補助）→ border（区切り）の3段階で迷いなく決める。新しい色を追加する前に、既存の3色で表現できないか考える
3. **コンポーネント選択**: カードよりリスト、モーダルよりインライン表示、アイコンよりテキストラベルを優先する
4. **日本語テキスト**: 本文 line-height は 1.9。0.9375rem（body）以上で表示する。カード内に長文を詰め込まない
5. **テーマ対応**: CSS変数で色を定義し、`:root` と `:root.dark` で切り替える。ハードコードの色値は使わない
6. **迷ったら**: シンプルな方を選ぶ。装飾を足すより、不要な要素を減らす方向で判断する
