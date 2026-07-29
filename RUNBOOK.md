# 데일리 브리핑 실행 절차 (자동 실행용)

이 문서는 매 평일 13:00 KST에 실행되는 예약 작업이 따르는 절차입니다.
예약 작업 프롬프트는 이 레포를 clone한 뒤 이 파일을 읽고 그대로 수행합니다.
절차를 바꾸고 싶으면 **이 파일과 `scripts/`만 수정**하면 됩니다 — 예약 작업은 건드릴 필요 없습니다.

전제: 레포는 이미 `/home/claude/repo` 에 clone되어 있고, 환경변수 `GH_TOKEN` 이 설정되어 있음.
작업 폴더는 `/home/claude/work` 를 씁니다 (`mkdir -p /home/claude/work/out`).

---

## 1단계 — 오늘의 신규 논문 목록

**경로 A (기본).** GitHub Actions 워크플로 `arXiv hep-th 수집`이 매 평일 **09:35 및 10:35 KST**에
`arxiv.org/list/hep-th/new`(공지 확정 목록)를 파싱해 `data/<공지날짜>.json` 을 커밋해 둡니다.
이 파일이 있으면 그대로 씁니다 — WebFetch도, 캐시 회피도, 추출 서브에이전트도 필요 없습니다.

> RSS는 13:00~13:06 KST에야 빌드되지만 `/list/new` 는 공지 시각(09:00 KST)에 갱신됩니다.
> 그래서 브리핑을 오전(11:00 KST)으로 당길 수 있습니다.
> cron이 두 개인 것은 서머타임 때문입니다 — 공지가 EDT면 09:00, EST면 10:00 KST라
> 유효하지 않은 쪽은 전날 목록과 동일하다고 판정돼 커밋 없이 끝납니다. 실측 대조: 2026-07-29분 23편, RSS와 ID 23/23 일치.
> 실행 로그는 `data/_last_run.txt` 에 매번 커밋되니 문제 시 이 파일부터 볼 것.

```bash
TODAY=$(TZ=Asia/Seoul date +%F)
ls -la /home/claude/repo/data/
python3 /home/claude/repo/scripts/split_chunks.py /home/claude/repo/data/$TODAY.json 6
```

`split_chunks.py` 가 `/home/claude/work/in/chunk{N}.json` 을 만들고 편수를 출력합니다.
이 편수가 곧 `TOTAL_NEW` 이고, 파일 안의 `date` 가 공지 날짜입니다.
성공했으면 **2단계-A** 로 갑니다.

**경로 B (폴백).** `data/$TODAY.json` 이 없으면 먼저 `data/_last_run.txt` 로 수집 실패 원인을 확인합니다.
그다음 `WebFetch` 로 **`https://arxiv.org/list/hep-th/new`** 를 직접 읽어 `New submissions` 절만 추출합니다.

> ⚠️ **이 시간대에 RSS를 쓰면 안 됩니다.** 브리핑은 11:00 KST에 도는데 RSS 피드는 13:00~13:06 KST에야
> 빌드되므로, 그 전에 부르면 **전날 목록**이 옵니다. 아래 RSS 절차는 13:00 KST 이후 재시도할 때만 유효합니다.
> arxiv.org는 429가 잦으니 걸리면 60~90초 대기 후 재시도할 것.

마지막 메시지에 "Actions 수집이 없어 폴백을 썼다"와 그 원인을 한 줄 덧붙입니다.

`WebFetch` 도구만 사용합니다. 이 컨테이너의 bash/curl로는 arxiv.org에 접근할 수 없습니다.
(필요하면 `ToolSearch` 로 `select:WebFetch` 먼저 로드)

URL: `https://rss.arxiv.org/rss/hep-th?d=<오늘 날짜 YYYY-MM-DD>`

> **`?d=` 를 반드시 붙일 것.** WebFetch 계층이 URL 단위로 응답을 오래 캐시합니다.
> 파라미터 없이 부르면 몇 주 전 피드가 그대로 돌아옵니다(실측: 7월 27일에 6월 30일자 피드 반환).
> 날짜를 파라미터로 넣으면 매일 새 캐시 키가 되어 항상 당일 피드를 받습니다.
> 받은 뒤 `lastBuildDate` 가 오늘인지 확인하세요. 오늘이 아니면 `?d=` 값에 시각까지 덧붙여 다시 부릅니다.
> 2~5단계에서 같은 피드를 다시 부를 때는 **1단계와 똑같은 `?d=` 값**을 써야 같은 스냅샷을 봅니다.

arXiv는 이 피드를 매일 **04:00 UTC(13:00 KST)** 에 새로 빌드합니다. 그 전에 부르면 전날/주말 피드가 옵니다.
주말(토·일) 피드는 항목이 0개입니다 — 정상입니다.

WebFetch prompt:

> This is an RSS feed. Output a plain list of EVERY item whose announce_type is exactly "new" (exclude cross, replace, replace-cross). For each, output one line: `ARXIVID | TITLE`. Do not summarize, do not skip any, do not add commentary. At the end output `TOTAL_NEW=<count>` and `FEED_PUBDATE=<the channel pubDate>`.

- `FEED_PUBDATE` 를 기록 → 브리핑의 공지 날짜로 사용 (`YYYY-MM-DD` 와 `2026년 6월 30일 (화)` 두 형식 모두 필요).
- `manifest.json` 에 같은 date가 이미 있으면 갱신(덮어쓰기)됩니다. 중복 걱정 없이 진행하세요.
- 신규 논문이 0편이면 그 사실만 짧게 알리고 종료.

## 2단계-A — 병렬 서브에이전트로 한국어 번역 (경로 A일 때)

`split_chunks.py` 가 만든 청크 수만큼 `Agent`(subagent_type: `general-purpose`)를
**한 메시지에서 동시에** 띄웁니다. 프롬프트는 아래를 그대로 쓰되 `{N}` 만 채웁니다.
추출이 이미 끝나 있으므로 WebFetch를 쓰지 않습니다 — 번역만 합니다.

> You are translating arXiv hep-th abstracts into Korean.
>
> STEP 1. Read `/home/claude/work/in/chunk{N}.json` — a JSON array of papers with keys
> `id, title, authors, categories, abstract`.
>
> STEP 2. For each paper write a Korean translation of the abstract:
> - Natural, fluent academic Korean ("~한다/~이다" 평서체).
> - KEEP all technical/physics terminology in English (holography, entanglement entropy, black hole, CFT, AdS/CFT, Yang-Mills, supersymmetry, moduli, brane, S-matrix, stress tensor, gauge theory, Calabi-Yau, renormalization, ...). Keep all math notation, LaTeX, symbols and arXiv IDs exactly as in the original.
> - Do not translate proper nouns or model names.
> - Translate the FULL abstract sentence for sentence. Never summarize.
>
> STEP 3. Write `/home/claude/work/out/chunk{N}.json` — the SAME array with an added
> `abstract_ko` key on each object. Copy `id, title, authors, categories, abstract` verbatim
> from the input; do not edit or re-wrap them.
> Validate: `python3 -c "import json;d=json.load(open('/home/claude/work/out/chunk{N}.json'));print(len(d), all(p.get('abstract_ko') for p in d))"`
>
> Return ONLY the string "chunk{N} done: N papers". Do not return paper content.

## 2단계-B — 병렬 서브에이전트로 추출 + 한국어 번역 (폴백 경로 B일 때)

ID를 **6개씩** 묶고, 청크마다 `Agent`(subagent_type: `general-purpose`)를 **한 메시지에서 동시에** 띄웁니다.
서브에이전트 프롬프트는 아래를 그대로 쓰되 `{IDS}`, `{N}`, `{DATE}`(1단계와 같은 `?d=` 값) 만 채웁니다.

> You are extracting arXiv hep-th paper data and translating abstracts to Korean.
>
> STEP 1. Call WebFetch (load via ToolSearch `select:WebFetch` if needed) on `https://rss.arxiv.org/rss/hep-th?d={DATE}` — use the exact same `?d=` value the caller gives you — with this prompt:
>
> "For ONLY these arXiv IDs: {IDS} — output verbatim from the feed, no summarizing, no paraphrasing, for each ID in this exact block format:
> ID: <id>
> TITLE: <title verbatim>
> AUTHORS: <full dc:creator list verbatim, comma separated>
> CATEGORIES: <all category terms for that item, comma separated>
> ABSTRACT: <the complete abstract text word-for-word from the description field, with the 'arXiv:... Announce Type: ...' prefix stripped>
> ---
> Copy each abstract exactly and completely. Do not shorten anything."
>
> If any requested ID comes back missing or with an empty abstract, call WebFetch again for just those IDs.
>
> STEP 2. For each paper write a Korean translation of the abstract:
> - Natural, fluent academic Korean ("~한다/~이다" 평서체).
> - KEEP all technical/physics terminology in English (holography, entanglement entropy, black hole, CFT, AdS/CFT, Yang-Mills, supersymmetry, moduli, brane, S-matrix, stress tensor, gauge theory, Calabi-Yau, renormalization, ...). Keep all math notation, LaTeX, symbols and arXiv IDs exactly as in the original.
> - Do not translate proper nouns or model names.
> - Translate the FULL abstract sentence for sentence. Never summarize.
>
> STEP 3. Write `/home/claude/work/out/chunk{N}.json` — a JSON array of objects with keys `id, title, authors, categories, abstract, abstract_ko`.
> Validate: `python3 -c "import json;print(len(json.load(open('/home/claude/work/out/chunk{N}.json'))))"`
>
> Return ONLY the string "chunk{N} done: N papers". Do not return paper content.

## 3단계 — 병합 및 검증

```bash
cd /home/claude/work && python3 /home/claude/repo/scripts/merge.py
```

`out/chunk*.json` 을 병합해 `papers.json` 을 만들고 결측/부실 항목을 리포트합니다.
1단계의 `TOTAL_NEW` 와 개수가 다르거나, `MISSING` / `SHORT_KO` 가 출력되면 **해당 논문만** 서브에이전트로 다시 돌려 고친 뒤 재실행하세요.

## 4단계 — 커밋 & 푸시

```bash
cd /home/claude/work && GH_TOKEN=$GH_TOKEN python3 /home/claude/repo/scripts/sync_repo.py \
  cms1308/hep-th-arxiv papers.json <YYYY-MM-DD> "<2026년 6월 30일 (화) 형식>"
```

브리핑 HTML 생성 → `manifest.json` 갱신 → `index.html` 재생성 → commit → push 까지 한 번에 처리합니다.
출력 마지막 줄에 GitHub Pages URL이 찍힙니다.

## 5단계 — 사용자에게 전달

1. 채팅에 바로 보여줄 단독 버전을 만듭니다 (뒤로가기 링크 없는 버전):
   ```bash
   python3 /home/claude/repo/scripts/build_html.py papers.json "<날짜문자열>" \
     /home/claude/work/hep-th_<YYYY-MM-DD>.html --standalone
   ```
2. `SendUserFile` 로 그 파일을 `status:"normal"`, `display:"render"` 로 전송.
3. 마지막 메시지는 한국어 2~3문장: 공지 날짜, 신규 편수, 눈에 띄는 주제 흐름 한 줄, 그리고 Pages 링크
   `https://cms1308.github.io/hep-th-arxiv/`. 논문을 하나하나 나열하지는 마세요.

---

## 부록 A — 과거 날짜 백필 (GitHub Actions, 권장)

RSS는 최신 공지 하나만 담지만 **arXiv API는 과거를 다 줍니다.** 러너에서 API를 치므로
이 컨테이너의 egress 제한·robots 제약과 무관합니다.

1. GitHub → Actions → `arXiv hep-th 수집` → **Run workflow** → `date` 에 `YYYY-MM-DD` 입력.
2. 끝나면 `data/<날짜>.json` 이 커밋됩니다. 레포를 다시 pull 해서 1단계 경로 A부터 그대로 진행.

`--api` 모드는 공지일 D에 대해 제출시각 창을 `(D-1 직전 영업일 14:00 ET) ~ (D-1 14:00 ET)` 로
추정합니다(실측 검증: 월요일=1일치, 화요일=주말 3일치). **공휴일은 반영하지 못하므로 편수를 눈으로 확인**하고,
어긋나면 창을 직접 지정합니다:

```
python3 scripts/fetch_arxiv.py --api --date 2026-07-20 --from 202607161800 --to 202607171800
```

## 부록 B — 과거 날짜 백필 (alphaXiv, 대체 수단)

Actions를 못 쓰는 상황에서만 씁니다. (자동 실행이 아니라 사람이 요청할 때만)

1. **메타데이터** — `WebFetch` 로 `https://arxiv.org/list/hep-th/recent?skip=0&show=<N>` 을 열고,
   원하는 날짜 heading 아래의 `New submissions` / `Cross-lists` 구분과 각 항목의
   ID · TITLE · AUTHORS · SUBJECTS 를 verbatim으로 받습니다. **New submissions만** 씁니다.
   (더 과거는 `?skip=` 을 늘려 페이지를 넘깁니다. 이 페이지에는 abstract가 없습니다.)
   Subjects 줄을 짧은 코드(`hep-th, gr-qc` 형태)로 정리해 `/home/claude/work/meta.json` 에 저장.

2. **abstract** — 논문 2편씩 묶어 서브에이전트를 병렬로 띄우고, 각자
   `mcp__alphaXiv__get_paper_content` (url `https://arxiv.org/abs/<id>`) 로 본문을 받아
   Abstract 문단만 추출합니다. PDF 추출 텍스트라 줄바꿈·하이픈 분리·수식 공백이 깨져 있으니
   문장은 그대로 두고 그 아티팩트만 복원하도록 지시할 것. 번역 규칙은 2단계와 동일.
   title/authors/categories 는 `meta.json` 에서 **verbatim으로 복사**하게 합니다.

3. 이후 3~5단계는 동일합니다.

주의: `arxiv.org` 는 자주 429 rate limit에 걸립니다. WebFetch 호출은 아껴 쓰고, 걸리면 60~90초 대기 후 재시도.
`export.arxiv.org` API는 이 환경에서 두 경로 모두 막혀 있습니다(컨테이너 egress 미허용 + robots.txt 거부).

## 문제 발생 시

- `data/$TODAY.json` 이 없으면 → 1단계 경로 B(WebFetch 폴백)로 진행하고 그 사실을 보고.
  주말이면 Action이 아예 안 도는 게 정상입니다.
- Action이 실패했으면 → GitHub Actions 탭의 로그를 알리고, 그날은 폴백으로 처리.
- 항목이 0개면 → 주말이거나 공지 전입니다. 그 사실만 알리고 종료 (커밋하지 말 것).
- `FEED_PUBDATE` 가 오늘과 어긋나면 → **거의 확실히 캐시 문제입니다.** `?d=` 값에 시각을 덧붙여
  (`?d=2026-07-27T1330`) 다시 부르세요. 그래도 안 고쳐지면 그대로 진행하되 마지막 메시지에
  "피드가 X일자로 잡혔다"고 한 줄 덧붙일 것.
- git push 실패 (401/403) → 토큰 만료 가능성. HTML은 `SendUserFile` 로 보내고, 토큰 재발급이 필요하다고 알릴 것.
