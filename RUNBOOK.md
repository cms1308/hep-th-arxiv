# 데일리 브리핑 실행 절차 (자동 실행용)

이 문서는 매 평일 13:00 KST에 실행되는 예약 작업이 따르는 절차입니다.
예약 작업 프롬프트는 이 레포를 clone한 뒤 이 파일을 읽고 그대로 수행합니다.
절차를 바꾸고 싶으면 **이 파일과 `scripts/`만 수정**하면 됩니다 — 예약 작업은 건드릴 필요 없습니다.

전제: 레포는 이미 `/home/claude/repo` 에 clone되어 있고, 환경변수 `GH_TOKEN` 이 설정되어 있음.
작업 폴더는 `/home/claude/work` 를 씁니다 (`mkdir -p /home/claude/work/out`).

---

## 1단계 — 오늘의 신규 논문 목록

`WebFetch` 도구만 사용합니다. 이 컨테이너의 bash/curl로는 arxiv.org에 접근할 수 없습니다.
(필요하면 `ToolSearch` 로 `select:WebFetch` 먼저 로드)

URL: `https://rss.arxiv.org/rss/hep-th`

WebFetch prompt:

> This is an RSS feed. Output a plain list of EVERY item whose announce_type is exactly "new" (exclude cross, replace, replace-cross). For each, output one line: `ARXIVID | TITLE`. Do not summarize, do not skip any, do not add commentary. At the end output `TOTAL_NEW=<count>` and `FEED_PUBDATE=<the channel pubDate>`.

- `FEED_PUBDATE` 를 기록 → 브리핑의 공지 날짜로 사용 (`YYYY-MM-DD` 와 `2026년 6월 30일 (화)` 두 형식 모두 필요).
- `manifest.json` 에 같은 date가 이미 있으면 갱신(덮어쓰기)됩니다. 중복 걱정 없이 진행하세요.
- 신규 논문이 0편이면 그 사실만 짧게 알리고 종료.

## 2단계 — 병렬 서브에이전트로 추출 + 한국어 번역

ID를 **6개씩** 묶고, 청크마다 `Agent`(subagent_type: `general-purpose`)를 **한 메시지에서 동시에** 띄웁니다.
서브에이전트 프롬프트는 아래를 그대로 쓰되 `{IDS}` 와 `{N}` 만 채웁니다.

> You are extracting arXiv hep-th paper data and translating abstracts to Korean.
>
> STEP 1. Call WebFetch (load via ToolSearch `select:WebFetch` if needed) on `https://rss.arxiv.org/rss/hep-th` with this prompt:
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

## 문제 발생 시

- arXiv 공지가 아직 갱신되지 않아 목록이 비어 있으면 → 그 사실만 알리고 종료.
- `FEED_PUBDATE` 가 오늘과 크게 어긋나면(예: 한 달 전) → 그대로 진행하되 마지막 메시지에 그 사실을 한 줄 덧붙일 것.
- git push 실패 (401/403) → 토큰 만료 가능성. HTML은 `SendUserFile` 로 보내고, 토큰 재발급이 필요하다고 알릴 것.
