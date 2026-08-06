# 데일리 브리핑 운영 문서

## 실행 경로

| 경로 | 무엇이 | 언제 |
|---|---|---|
| `.github/workflows/daily-brief.yml` | 수집·번역·발행 전부 러너에서 | 매 평일 11:17 KST 목표. **주 자동화.** |
| `scripts/run_local.sh` | 같은 일을 이 맥에서 | 정시 실행이 필요하거나 워크플로가 실패한 날 |

Actions 경로는 Claude Max 구독 OAuth 토큰을 씁니다. `claude setup-token` 으로 발급해
레포 Secret `CLAUDE_CODE_OAUTH_TOKEN` 에 등록해 두어야 합니다.

`run_local.sh` 의 작업 폴더는 `$BRIEF_WORK` (기본 `~/.hep-th-brief-work`), 로그는 그 아래 `logs/`.

## 파이프라인

```
fetch_arxiv.py   arxiv.org/list/hep-th/new 파싱 → data/<공지일>.json
split_chunks.py  $BRIEF_WORK/in/chunk{N}.json 으로 분할
(Claude)         논문마다 $BRIEF_WORK/out/<arXiv id>.txt 에 한국어 번역만 씀
merge_ko.py      원본 json + 번역 txt → papers.json, 결측·부실 리포트 (문제 있으면 exit 1)
sync_repo.py     build_html → manifest 갱신 → build_index → commit → push
```

번역을 **JSON 이 아니라 텍스트 파일**로 받는 이유: 모델이 abstract 의 LaTeX 를 verbatim
복사하며 JSON 을 손으로 쓰면 백슬래시·따옴표 이스케이프가 깨집니다
(실측 2026-08-05: 4청크 중 3청크가 `BAD_JSON`). 합치는 일은 `merge_ko.py` 가 합니다.

## 타이밍

arXiv 공지는 **20:00 ET, 일~목요일** (금·토 없음) — 서머타임이면 09:00 KST,
겨울이면 10:00 KST 입니다. 다만 `/list/new` 페이지가 그 공지를 *언제* 반영하는지는
arXiv 가 문서화하지 않았고 실제로 지연이 있습니다. 연휴에는 공지 자체가 순연됩니다.
([Availability of submissions](https://info.arxiv.org/help/availability.html) ·
[arxiv.org/localtime](https://arxiv.org/localtime))

그래서 시각을 가정하지 않습니다. `fetch_arxiv.py --expect <날짜>` 가 받아온 목록이
이미 저장된 다른 날짜와 동일하면 "아직 갱신 전" 으로 보고 재시도합니다
(현재 30분 간격 3회: 11:17 / 11:47 / 12:17).

GitHub schedule 도 정시에 오지 않습니다 (실측: 00:35 UTC cron 이 03:41·04:36 UTC 발화,
미발화한 날도 있었음). 늦게 발화해도 `--expect` 덕분에 날짜는 어긋나지 않습니다.

## 과거 날짜 백필

`/list/new` 는 최신 공지만 담으므로 빠진 날짜는 arXiv API 로 채웁니다.
Actions 탭 → **hep-th 데일리 브리핑** → Run workflow → `date` 에 `YYYY-MM-DD` 입력.
(`date` 를 주면 워크플로가 `fetch_arxiv.py --api --date` 로 돕니다.)

API 모드는 공지일 D 의 제출시각 창을 `(D-1 직전 영업일 18:00 UTC) ~ (D-1 18:00 UTC)` 로
추정합니다. **공휴일은 반영하지 못하므로 편수를 눈으로 확인**하고, 어긋나면 직접 지정:

```
python3 scripts/fetch_arxiv.py --api --date 2026-07-20 --from 202607161800 --to 202607171800
```

## 문제 발생 시

워크플로가 실패하면 `brief-failure` 라벨이 붙은 이슈가 자동 생성되고 GitHub 이 메일을 보냅니다.
같은 날짜 이슈가 이미 열려 있으면 코멘트만 달립니다.

- **인증 에러** → OAuth 토큰 만료. `claude setup-token` 재발급 후 Secret
  `CLAUDE_CODE_OAUTH_TOKEN` 갱신.
- **`MISSING` / `SHORT_KO`** → 번역 누락·부실. 워크플로가 해당 논문만 자동 재번역하고
  재검증합니다. 재번역 후에도 실패하면 로그의 arXiv id 를 확인하세요.
- **12시까지 전날 목록** → 커밋 없이 조용히 종료합니다 (공지 순연이거나 휴일).
  알림은 가지 않으므로, 브리핑이 안 올라온 날은 Actions 탭 로그를 보세요.
- **커밋은 됐는데 push 실패** → `sync_repo.py` 가 git stderr 를 그대로 출력합니다.
  번역 스텝이 git 자격증명을 건드리므로 발행 스텝에서 origin 인증을 다시 붙입니다.
