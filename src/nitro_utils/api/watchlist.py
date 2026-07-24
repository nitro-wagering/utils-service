import csv
import io
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, ORJSONResponse, StreamingResponse
from kubernetes import client, config  # type: ignore[import-untyped]
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel

from nitro_utils.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistEntry(BaseModel):
    track: str
    race_number: int
    race_time: str
    horse: str
    our_win: float
    win_pct: float
    win_trigger: float
    our_place: float
    place_pct: float
    place_trigger: float
    win_overlay_pct: float | None
    win_distance_to_trigger: float | None
    market_win: float | None
    market_place: float | None
    market_rank: int | None
    place_overlay_pct: float | None
    place_distance_to_trigger: float | None
    neds_win: float | None
    neds_place: float | None
    class_rank: int
    sim_order: int | None
    pf_time_rank: int | None
    in_monitor_net: str
    placed: str


class WatchlistResponse(BaseModel):
    generated_at: str
    entry_count: int
    entries: list[WatchlistEntry]


def _parse_watchlist_csv(csv_path: Path) -> list[WatchlistEntry]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Watchlist CSV not found at {csv_path}")

    entries: list[WatchlistEntry] = []

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                entries.append(
                    WatchlistEntry(
                        track=row["Track"],
                        race_number=int(row["Race #"]),
                        race_time=row["Race Time"],
                        horse=row["Horse"],
                        our_win=float(row["Our Win"]),
                        win_pct=float(row["Win %"]),
                        win_trigger=float(row["WIN Trigger"]),
                        our_place=float(row["Our Place"]),
                        place_pct=float(row["Place %"]),
                        place_trigger=float(row["PLACE Trigger"]),
                        win_overlay_pct=float(row["Win Overlay %"]) if row.get("Win Overlay %") else None,
                        win_distance_to_trigger=(
                            float(row["Win Distance to Trigger"])
                            if row.get("Win Distance to Trigger")
                            else None
                        ),
                        market_win=float(row["Market Win"]) if row.get("Market Win") else None,
                        market_place=float(row["Market Place"]) if row.get("Market Place") else None,
                        market_rank=int(row["Market Rank"]) if row.get("Market Rank") else None,
                        place_overlay_pct=(
                            float(row["Place Overlay %"]) if row.get("Place Overlay %") else None
                        ),
                        place_distance_to_trigger=(
                            float(row["Place Distance to Trigger"])
                            if row.get("Place Distance to Trigger")
                            else None
                        ),
                        neds_win=float(row["Neds Win"]) if row.get("Neds Win") else None,
                        neds_place=float(row["Neds Place"]) if row.get("Neds Place") else None,
                        class_rank=int(row["Class Rank"]),
                        sim_order=int(row["Sim Order"]) if row.get("Sim Order") else None,
                        pf_time_rank=int(row["PF Time Rank"]) if row.get("PF Time Rank") else None,
                        in_monitor_net=row["In Monitor Net"],
                        placed=row["PLACED"],
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Failed to parse CSV row: %s — error: %s", row, e)
                continue

    return entries


def _render_html_table(entries: list[WatchlistEntry]) -> str:
    rows_html = ""
    for entry in entries:
        rows_html += f"""
        <tr>
            <td>{entry.track}</td>
            <td>{entry.race_number}</td>
            <td>{entry.race_time}</td>
            <td>{entry.horse}</td>
            <td>{entry.our_win:.2f}</td>
            <td>{entry.win_pct:.1f}%</td>
            <td>{entry.win_overlay_pct:.1f}% if entry.win_overlay_pct is not None else '-'}</td>
            <td>{entry.win_distance_to_trigger:.2f if entry.win_distance_to_trigger is not None else '-'}</td>
            <td>{entry.market_win:.2f if entry.market_win is not None else '-'}</td>
            <td>{entry.placed}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Watchlist - Nitro Wagering</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; position: sticky; top: 0; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .header {{ margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Watchlist</h1>
        <p>Last updated: {datetime.now(timezone.utc).isoformat()}</p>
        <p>Total entries: {len(entries)}</p>
    </div>
    <table>
        <thead>
            <tr>
                <th>Track</th>
                <th>Race</th>
                <th>Time</th>
                <th>Horse</th>
                <th>Our Win</th>
                <th>Win %</th>
                <th>Overlay %</th>
                <th>Distance to Trigger</th>
                <th>Market Win</th>
                <th>Placed</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>"""


@router.get("", response_model=WatchlistResponse)
async def get_watchlist() -> WatchlistResponse | HTMLResponse:
    csv_path = Path(settings.watchlist_csv_path)

    try:
        entries = _parse_watchlist_csv(csv_path)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Watchlist data unavailable")
    except Exception as e:
        logger.exception("Failed to parse watchlist CSV")
        raise HTTPException(status_code=500, detail=f"Failed to load watchlist: {e}")

    stat = csv_path.stat()
    generated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

    return WatchlistResponse(
        generated_at=generated_at,
        entry_count=len(entries),
        entries=entries,
    )


@router.post("/refresh")
async def refresh_watchlist() -> dict[str, Any]:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except config.ConfigException:
            raise HTTPException(status_code=500, detail="Kubernetes config unavailable")

    batch_v1 = client.BatchV1Api()
    job_name = f"watchlist-refresh-{secrets.token_hex(4)}"

    job_manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name, "namespace": settings.k8s_namespace},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "refresh",
                            "image": settings.k8s_job_image,
                            "command": ["python3", "/tmp/build_watchlist_final.py"],
                            "env": [
                                {
                                    "name": "NITRO_DATABASE_URL",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "nitro-secrets",
                                            "key": "database-url",
                                        }
                                    },
                                }
                            ],
                            "volumeMounts": [
                                {"name": "shared", "mountPath": "/shared"},
                                {"name": "workspace", "mountPath": "/workspace"},
                            ],
                        }
                    ],
                    "volumes": [
                        {"name": "shared", "persistentVolumeClaim": {"claimName": "nitro-shared"}},
                        {
                            "name": "workspace",
                            "persistentVolumeClaim": {"claimName": "paper-monitor-workspace"},
                        },
                    ],
                    "restartPolicy": "OnFailure",
                }
            },
            "backoffLimit": 2,
        },
    }

    try:
        batch_v1.create_namespaced_job(namespace=settings.k8s_namespace, body=job_manifest)
        logger.info("Created watchlist refresh job: %s", job_name)
        return {"status": "triggered", "job_name": job_name}
    except Exception as e:
        logger.exception("Failed to create watchlist refresh job")
        raise HTTPException(status_code=500, detail=f"Failed to trigger refresh: {e}")


@router.get("/download")
async def download_watchlist() -> StreamingResponse:
    csv_path = Path(settings.watchlist_csv_path)

    try:
        entries = _parse_watchlist_csv(csv_path)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Watchlist data unavailable")
    except Exception as e:
        logger.exception("Failed to parse watchlist CSV")
        raise HTTPException(status_code=500, detail=f"Failed to load watchlist: {e}")

    wb = Workbook()
    ws: Worksheet = wb.active  # type: ignore[assignment]
    ws.title = "Watchlist"

    headers = [
        "Track",
        "Country",
        "Race #",
        "Race Time",
        "Horse",
        "Our Win",
        "Win %",
        "Neds Win",
        "Our Place",
        "Place %",
        "Neds Place",
        "Bet Placed",
        "Bet Type",
        "Odds Taken",
        "Stake (AUD)",
        "Result Position",
        "Payout (AUD)",
        "Profit (AUD)",
        "ROI %",
    ]

    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True)  # type: ignore[misc]

    for entry in entries:
        ws.append(
            [
                entry.track,
                "AUS",  # TODO: extract from data once country field available
                entry.race_number,
                entry.race_time,
                entry.horse,
                entry.our_win,
                entry.win_pct,
                entry.neds_win if entry.neds_win else "",
                entry.our_place,
                entry.place_pct,
                entry.neds_place if entry.neds_place else "",
                "",  # Bet Placed (user fills)
                "",  # Bet Type (user fills)
                "",  # Odds Taken (user fills)
                "",  # Stake (user fills)
                "",  # Result Position (computed post-race)
                "",  # Payout (computed post-race)
                "",  # Profit (computed post-race)
                "",  # ROI % (computed post-race)
            ]
        )

    for i in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 15

    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)

    filename = f"watchlist-{datetime.now(timezone.utc).strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class UploadResult(BaseModel):
    status: str
    imported_bets: int
    errors: list[str]


class BetRequest(BaseModel):
    race_id: int
    race_date: str  # ISO date string (YYYY-MM-DD)
    horse_name: str
    track_name: str
    race_number: int
    bet_type: str  # "win" | "place" | "each_way"
    odds_taken: float
    stake_aud: float


class BetResponse(BaseModel):
    status: str
    bet_id: int


class PayoutUpdateRequest(BaseModel):
    payout_aud: float


class PayoutUpdateResponse(BaseModel):
    status: str
    profit_aud: float
    roi_pct: float


@router.post("/upload", response_model=UploadResult)
async def upload_watchlist(file: UploadFile = File(...)) -> UploadResult:
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be .xlsx format")

    try:
        from openpyxl import load_workbook

        contents = await file.read()
        wb = load_workbook(io.BytesIO(contents))
        ws = wb.active

        headers_row = [cell.value for cell in ws[1]]  # type: ignore[index]
        expected_headers = [
            "Track",
            "Country",
            "Race #",
            "Race Time",
            "Horse",
            "Our Win",
            "Win %",
            "Neds Win",
            "Our Place",
            "Place %",
            "Neds Place",
            "Bet Placed",
            "Bet Type",
            "Odds Taken",
            "Stake (AUD)",
            "Result Position",
            "Payout (AUD)",
            "Profit (AUD)",
            "ROI %",
        ]

        if headers_row != expected_headers:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid headers. Expected: {expected_headers}",
            )

        imported_count = 0
        errors: list[str] = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):  # type: ignore[arg-type]
            try:
                bet_placed = str(row[11]).strip().upper() if row[11] else ""
                if bet_placed not in ("YES", "Y", "TRUE", "1"):
                    continue

                track = str(row[0]).strip() if row[0] else None
                horse = str(row[4]).strip() if row[4] else None
                bet_type = str(row[12]).strip().lower() if row[12] else None
                odds_taken = float(row[13]) if row[13] else None
                stake = float(row[14]) if row[14] else None

                if not all([track, horse, bet_type, odds_taken, stake]):
                    errors.append(f"Row {row_idx}: Missing required bet fields")
                    continue

                if bet_type not in ("win", "place", "each_way"):
                    errors.append(f"Row {row_idx}: Invalid bet type '{bet_type}'")
                    continue

                if odds_taken <= 0 or stake <= 0:  # type: ignore[operator]
                    errors.append(f"Row {row_idx}: Odds and stake must be positive")
                    continue

                logger.info(
                    "Parsed bet from upload: track=%s horse=%s type=%s odds=%s stake=%s",
                    track,
                    horse,
                    bet_type,
                    odds_taken,
                    stake,
                )
                imported_count += 1

            except (ValueError, TypeError) as e:
                errors.append(f"Row {row_idx}: Parse error - {e}")
                continue

        logger.info("Upload processing complete: %d bets imported, %d errors", imported_count, len(errors))

        return UploadResult(
            status="ok",
            imported_bets=imported_count,
            errors=errors[:20],
        )

    except Exception as e:
        logger.exception("Failed to process uploaded file")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {e}")


@router.post("/bets", response_model=BetResponse)
async def create_bet(bet: BetRequest) -> BetResponse:
    if bet.bet_type not in ("win", "place", "each_way"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bet_type '{bet.bet_type}'. Must be win, place, or each_way.",
        )

    if bet.odds_taken <= 0:
        raise HTTPException(status_code=400, detail="odds_taken must be positive")

    if bet.stake_aud <= 0:
        raise HTTPException(status_code=400, detail="stake_aud must be positive")

    try:
        from datetime import date

        date.fromisoformat(bet.race_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="race_date must be ISO format (YYYY-MM-DD)")

    logger.info(
        "Create bet: user_id=TODO race_id=%d horse=%s type=%s odds=%s stake=%s",
        bet.race_id,
        bet.horse_name,
        bet.bet_type,
        bet.odds_taken,
        bet.stake_aud,
    )

    return BetResponse(status="ok", bet_id=999)


@router.delete("/bets/{bet_id}")
async def delete_bet(bet_id: int) -> dict[str, str]:
    logger.info("Delete bet: bet_id=%d user_id=TODO", bet_id)

    return {"status": "ok"}


@router.put("/bets/{bet_id}/payout", response_model=PayoutUpdateResponse)
async def update_payout(bet_id: int, payload: PayoutUpdateRequest) -> PayoutUpdateResponse:
    if payload.payout_aud < 0:
        raise HTTPException(status_code=400, detail="payout_aud cannot be negative")

    logger.info("Update payout: bet_id=%d payout=%s user_id=TODO", bet_id, payload.payout_aud)

    stake_aud = 10.0
    profit_aud = payload.payout_aud - stake_aud
    roi_pct = (profit_aud / stake_aud) * 100 if stake_aud > 0 else 0.0

    return PayoutUpdateResponse(
        status="ok",
        profit_aud=round(profit_aud, 2),
        roi_pct=round(roi_pct, 2),
    )
