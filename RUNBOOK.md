# 데일리 브리핑 실행 절차 (자동 실행용)

매 평일 11:00 KST에 실행되는 예약 작업이 따르는 절차입니다.
예약 작업 프롬프트는 이 레포를 clone한 뒤 이 파일을 읽고 그대로 수행합니다.
절차를 바꾸려면 **이 파일과 `scripts/` 만 수정**하면 됩니다 — 예약 작업은 건드릴 필요 없습니다.

전제: 레포가 `/home/claude/repo` 에 clone돼 있고, 환경변수 `GH_TOKEN` 이 설정돼 있음.
작업 폴더는 `/home/claude/work` (`mkdir -p /home/claude/work/out`).

**원칙: arXiv는 GitHub Actions 러너에서만 호출합니다.**
브리핑 컨테이너의 `WebFetch` 는 arxiv.org 응답을 오래 캐시해 날짜가 틀린 목록을 조용히 돌려줍니다
(실측 2026-07-31 11시: `/list/hep-th/new` → 전날 목록, `/list/hep-th/recent` → 7월 20일자.
`?d=`·`?skip=`·`?show=` 로 URL을 바꿔도 동일). RSS도 쓰지 않습니다 — 13:00 KST에야 빌드돼
오전에 부르면 전날 것이 옵니다.

cron도 쓰지 않습니다. GitHub schedule은 수 시간까지 밀립니다(실측: 00:35 UTC cron이
2026-07-30에 03:41·04:36 UTC 발화, 07-31에는 11:00 KST까지 미발화). 세션이 직접 띄우고
기다리는 편이 확실합니다.

---

## 1단계 — 오늘의 신규 논문 목록

```bash
cd /home/claude/repo && GH_TOKEN=$GH_TOKEN python3 scripts/collect.py
TODAY=$(TZ=Asia/Seoul date +%F)
python3 /home/claude/repo/scripts/split_chunks.py /home/claude/repo/data/$TODAY.json 6
```

`collect.py` 가 알아서 처리합니다:

1. `git pull` 후 `data/<오늘>.json` 이 있으면 그대로 씁니다.
2. 없으면 `.trigger` 를 push해 수집 워크플로를 띄우고, 결과 커밋이 올 때까지 폴링합니다
   (기본 최대 15분, 45초 간격). 보통 1~2분이면 끝납니다.
3. 실패하면 `data/_last_run.txt` 를 출력하고 0이 아닌 코드로 종료합니다.

`split_chunks.py` 가 `/home/claude/work/in/chunk{N}.json` 을 만들고 편수를 출력합니다.
이 편수가 `TOTAL_NEW` 이고, 파일 안의 `date` 가 공지 날짜입니다.

- 신규 0편이면 주말이거나 아직 공지 전입니다. 그 사실만 짧게 알리고 **커밋 없이 종료**합니다.
- `manifest.json` 에 같은 date가 이미 있으면 갱신(덮어쓰기)됩니다. 중복 걱정 없이 진행하세요.

## 2단계 — 병렬 서브에이전트로 한국어 번역

`split_chunks.py` 가 만든 청크 수만큼 `Agent`(subagent_type: `general-purpose`)를
**한 메시지에서 동시에** 띄웁니다. 프롬프트는 아래를 그대로 쓰되 `{N}` 만 채웁니다.
추출은 이미 끝나 있으므로 웹 접근은 필요 없습니다 — 번역만 합니다.

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

## 3단계 — 병합 및 검증

```bash
cd /home/claude/work && python3 /home/claude/repo/scripts/merge.py
```

`out/chunk*.json` 을 병합해 `papers.json` 을 만들고 결측/부실 항목을 리포트합니다.
1단계의 `TOTAL_NEW` 와 개수가 다르거나 `MISSING` / `SHORT_KO` 가 나오면
**해당 논문만** 서브에이전트로 다시 돌려 고친 뒤 재실행하세요.

## 4단계 — 커밋 & 푸시

```bash
cd /home/claude/work && GH_TOKEN=$GH_TOKEN python3 /home/claude/repo/scripts/sync_repo.py \
  cms1308/hep-th-arxiv papers.json <YYYY-MM-DD> "<2026년 7월 31일 (금) 형식>"
```

브리핑 HTML 생성 → `manifest.json` 갱신 → `index.html` 재생성 → commit → push 를 한 번에 합니다.
마지막 줄에 GitHub Pages URL이 찍힙니다.

## 5단계 — 사용자에게 전달

1. 채팅용 단독 버전(뒤로가기 링크 없음)을 만듭니다:
   ```bash
   python3 /home/claude/repo/scripts/build_html.py papers.json "<날짜문자열>" \
     /home/claude/work/hep-th_<YYYY-MM-DD>.html --standalone
   ```
2. `SendUserFile` 로 `status:"normal"`, `display:"render"` 전송.
3. 마지막 메시지는 한국어 2~3문장: 공지 날짜, 신규 편수, 눈에 띄는 주제 흐름 한 줄,
   그리고 아카이브 링크 `https://cms1308.github.io/hep-th-arxiv/`.
   논문을 하나하나 나열하지는 마세요.

---

## 과거 날짜 백필

빠진 날짜가 있으면 (`/list/new` 는 최신 공지만 담으므로) arXiv API로 채웁니다.

```bash
cd /home/claude/repo && GH_TOKEN=$GH_TOKEN python3 scripts/collect.py --backfill 2026-07-24
```

`data/2026-07-24.json` 이 커밋되면 1단계 `split_chunks.py` 부터 그대로 진행하면 됩니다.
API 모드는 공지일 D의 제출시각 창을 `(D-1 직전 영업일 18:00 UTC) ~ (D-1 18:00 UTC)` 로
추정합니다. **공휴일은 반영하지 못하므로 편수를 눈으로 확인**하고, 어긋나면 러너에서 직접 지정:

```
python3 scripts/fetch_arxiv.py --api --date 2026-07-20 --from 202607161800 --to 202607171800
```

## 문제 발생 시

- **`collect.py` 가 타임아웃** → 출력된 `data/_last_run.txt` 를 보세요.
  - `항목 0편` / `... 와 동일한 목록` → 아직 공지 전이거나 휴일입니다. 그 사실을 알리고 종료.
  - 그 외 실패 → GitHub Actions 탭의 `arXiv hep-th 수집` 로그 확인.
- **`collect.py` 가 push에서 실패하거나 4단계 push가 401/403** → 토큰 만료 가능성.
  브리핑을 만들 수 있는 상태면 HTML을 `SendUserFile` 로 보내고, 토큰 재발급이 필요하다고 알릴 것.
- **워크플로가 안 돌 때** → 트리거는 `.trigger` push 하나뿐입니다.
  GitHub Actions 탭에서 워크플로가 비활성화(disabled)돼 있지 않은지 확인하세요.
- 브리핑 세션에서는 `api.github.com` 을 쓸 수 없습니다. 실행 상태는 항상 레포의
  `data/_last_run.txt` 로 확인합니다.
