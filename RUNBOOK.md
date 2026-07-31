# 데일리 브리핑 실행 절차 (자동 실행용)

이 문서는 매 평일 11:00 KST에 실행되는 예약 작업이 따르는 절차입니다.
예약 작업 프롬프트는 이 레포를 clone한 뒤 이 파일을 읽고 그대로 수행합니다.
절차를 바꾸고 싶으면 **이 파일과 `scripts/`만 수정**하면 됩니다 — 예약 작업은 건드릴 필요 없습니다.

전제: 레포는 이미 `/home/claude/repo` 에 clone되어 있고, 환경변수 `GH_TOKEN` 이 설정되어 있음.
작업 폴더는 `/home/claude/work` 를 씁니다 (`mkdir -p /home/claude/work/out`).

---

## 1단계 — 오늘의 신규 논문 목록

**경로 A (기본).** GitHub Actions 워크플로 `arXiv hep-th 수집`이 매 평일 **09:35 및 10:35 KST**에
`arxiv.org/list/hep-th/new`(공지 확정 목록)를 파싱해 `data/<공지날짜>.json` 을 커밋해 둡니다.
이 파일이 있으면 그대로 씁니다 — 추출 단계가 필요 없습니다.

> `/list/new` 는 공지 시각(20:00 ET = 09:00 KST)에 갱신되므로 브리핑을 오전 11:00 KST에 돌릴 수 있습니다.
> cron이 두 개인 것은 서머타임 때문입니다 — 공지가 EDT면 09:00, EST면 10:00 KST라
> 유효하지 않은 쪽은 전날 목록과 동일하다고 판정돼 커밋 없이 끝납니다.
> 실행 로그는 `data/_last_run.txt` 에 매번 커밋되니 문제 시 이 파일부터 볼 것.
> **cron은 믿을 수 없습니다** — 발동하지 않은 날이 관측됐으니 파일이 없으면 바로 경로 B로 갑니다.

```bash
TODAY=$(TZ=Asia/Seoul date +%F)
ls -la /home/claude/repo/data/
python3 /home/claude/repo/scripts/split_chunks.py /home/claude/repo/data/$TODAY.json 6
```

`split_chunks.py` 가 `/home/claude/work/in/chunk{N}.json` 을 만들고 편수를 출력합니다.
이 편수가 곧 `TOTAL_NEW` 이고, 파일 안의 `date` 가 공지 날짜입니다.
성공했으면 **2단계** 로 갑니다.

**경로 B (폴백) — 워크플로를 직접 깨운다.** `data/$TODAY.json` 이 없으면 먼저 `data/_last_run.txt` 로
마지막 실행 번호·시각·결과를 확인합니다. 그다음 `.trigger` 를 푸시해 수집 워크플로를 즉시 돌립니다.

```bash
cd /home/claude/repo
git config user.name "briefing-bot"; git config user.email "noreply@anthropic.com"
echo "--new --expect $TODAY --retries 3 --retry-wait 120" > .trigger
git add .trigger && git commit -q -m "trigger: $TODAY 수집 재시도" && git push -q
```

워크플로는 `.trigger` push에 걸려 있고 보통 1분 안에 끝납니다. `api.github.com` 은 이 토큰으로 읽을 수
없으므로(403) Actions API 대신 **레포를 polling** 해서 결과를 봅니다:

```bash
for i in $(seq 1 8); do
  git fetch -q origin && git reset -q --hard origin/main
  [ -f data/$TODAY.json ] && { echo "수집 완료"; break; }
  echo "poll $i — 아직 없음"; sleep 60
done
cat data/_last_run.txt
```

파일이 생기면 위 경로 A(`split_chunks.py`)로 그대로 이어갑니다.
마지막 메시지에 "예약 수집이 안 돌아 `.trigger` 로 수동 실행했다"를 한 줄 덧붙입니다.

> ⚠️ **WebFetch로 arxiv.org를 읽으려 하지 말 것.** WebFetch 계층이 arxiv 목록 페이지를 한 달 넘게
> stale하게 반환합니다(실측: 2026-07-30에 호출 → 2026-06-26자 목록. `?skip=&show=&v=` 로 URL을 바꿔
> 캐시를 우회해도 동일). 날짜가 틀린 목록이 조용히 그럴듯하게 돌아오므로, 없느니만 못한 경로입니다.
> arXiv에 실제로 도달할 수 있는 곳은 **GitHub Actions 러너뿐**이고, 그래서 폴백도 러너를 쓰는 방식입니다.

- 신규 논문이 0편이면(주말·공지 전) 그 사실만 짧게 알리고 종료. 커밋하지 않습니다.
- `manifest.json` 에 같은 date가 이미 있으면 갱신(덮어쓰기)됩니다. 중복 걱정 없이 진행하세요.

## 2단계 — 병렬 서브에이전트로 한국어 번역

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

## 부록 — 과거 날짜 백필 (GitHub Actions)

`/list/new` 는 최신 공지 하나만 담지만 **arXiv API는 과거를 다 줍니다.** 러너에서 API를 치므로
이 컨테이너의 egress 제한·robots 제약과 무관합니다.

1. GitHub → Actions → `arXiv hep-th 수집` → **Run workflow** → `date` 에 `YYYY-MM-DD` 입력.
2. 끝나면 `data/<날짜>.json` 이 커밋됩니다. 레포를 다시 pull 해서 1단계 경로 A부터 그대로 진행.

`--api` 모드는 공지일 D에 대해 제출시각 창을 `(D-1 직전 영업일 14:00 ET) ~ (D-1 14:00 ET)` 로
추정합니다(실측 검증: 월요일=1일치, 화요일=주말 3일치). **공휴일은 반영하지 못하므로 편수를 눈으로 확인**하고,
어긋나면 창을 직접 지정합니다:

```
python3 scripts/fetch_arxiv.py --api --date 2026-07-20 --from 202607161800 --to 202607171800
```

## 문제 발생 시

- `data/$TODAY.json` 이 없으면 → 1단계 **경로 B**(`.trigger` 푸시)로 진행하고 그 사실을 보고.
  주말이면 워크플로가 아예 안 도는 게 정상입니다.
- `_last_run.txt` 의 run 번호가 어제 것 그대로면 → 예약 cron이 **발동 자체를 안 한 것**입니다(실패가 아님).
  2026-07-30·07-31 이틀 연속 관측됐습니다. 경로 B로 처리하고, 반복되면 GitHub Actions 탭에서
  워크플로가 disabled 상태인지 확인할 것.
- 수집은 돌았는데 편수가 0이면 → 주말이거나 공지 전입니다. 그 사실만 알리고 종료 (커밋하지 말 것).
- `data/$TODAY.json` 의 `date` 가 오늘이 아니면 → 그대로 쓰지 말고 경로 B로 재수집.
- git push 실패 (401/403) → 토큰 만료 가능성. HTML은 `SendUserFile` 로 보내고, 토큰 재발급이 필요하다고 알릴 것.
