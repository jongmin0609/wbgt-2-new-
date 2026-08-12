import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from acclimatization import DEFAULT_ACCLIMATIZATION, validate_acclimatization_inputs
from measurement_store import DEFAULT_PROFILE, validate_measurement, validate_profile


BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("WGBT_DATA_DIR", BASE_DIR / "data"))
DEVICES_PATH = DATA_DIR / "devices.json"
WORKERS_PATH = DATA_DIR / "workers.json"
RISK_EVENTS_PATH = DATA_DIR / "risk_events.json"

ALERT_EVENT_LEVELS = {"경고", "위험"}


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
        newline="\n",
        suffix=".json",
    ) as temp_file:
        json.dump(payload, temp_file, ensure_ascii=False, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)

    temp_path.replace(path)


def read_json(path, fallback):
    if not path.exists():
        return fallback.copy() if isinstance(fallback, dict) else list(fallback)

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return fallback.copy() if isinstance(fallback, dict) else list(fallback)


def normalize_device_id(device_id):
    value = str(device_id or "").strip()
    if not value:
        return f"dev-{uuid.uuid4().hex}"
    return value[:120]


def normalize_worker_id(worker_number):
    value = str(worker_number or "").strip().upper()
    if not value:
        raise ValueError("작업자 번호를 입력해주세요.")
    return value[:40]


def validate_worker_identity(worker_number, name):
    worker_id = normalize_worker_id(worker_number)
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("작업자 이름을 입력해주세요.")
    return worker_id, normalized_name[:40]


def read_devices(path=DEVICES_PATH):
    devices = read_json(path, {})
    if not isinstance(devices, dict):
        return {}
    return devices


def write_devices(devices, path=DEVICES_PATH):
    atomic_write_json(path, devices)


def get_device(device_id, path=DEVICES_PATH):
    device_id = normalize_device_id(device_id)
    devices = read_devices(path)
    return devices.get(device_id, {"device_id": device_id, "role": "unregistered"})


def register_manager_device(device_id, path=DEVICES_PATH):
    device_id = normalize_device_id(device_id)
    devices = read_devices(path)
    timestamp = now_iso()
    devices[device_id] = {
        **devices.get(device_id, {}),
        "device_id": device_id,
        "role": "manager",
        "worker_id": None,
        "registered_at": devices.get(device_id, {}).get("registered_at", timestamp),
        "last_seen_at": timestamp,
    }
    write_devices(devices, path)
    return devices[device_id]


def register_worker_device(device_id, worker_id, path=DEVICES_PATH):
    device_id = normalize_device_id(device_id)
    worker_id = normalize_worker_id(worker_id)
    devices = read_devices(path)
    timestamp = now_iso()
    devices[device_id] = {
        **devices.get(device_id, {}),
        "device_id": device_id,
        "role": "worker",
        "worker_id": worker_id,
        "registered_at": devices.get(device_id, {}).get("registered_at", timestamp),
        "last_seen_at": timestamp,
    }
    write_devices(devices, path)
    return devices[device_id]


def touch_device(device_id, path=DEVICES_PATH):
    device_id = normalize_device_id(device_id)
    devices = read_devices(path)
    if device_id in devices:
        devices[device_id]["last_seen_at"] = now_iso()
        write_devices(devices, path)
        return devices[device_id]
    return {"device_id": device_id, "role": "unregistered"}


def read_workers(path=WORKERS_PATH):
    workers = read_json(path, {})
    if not isinstance(workers, dict):
        return {}
    return workers


def write_workers(workers, path=WORKERS_PATH):
    atomic_write_json(path, workers)


def get_worker(worker_id, path=WORKERS_PATH):
    worker_id = normalize_worker_id(worker_id)
    return read_workers(path).get(worker_id)


def validate_worker_payload(
    worker_number,
    name,
    age,
    weight,
    sex,
    worker_status,
    heat_exposure_days,
    absence_days,
    similar_heat_work,
    heart_rate,
    wbgt,
):
    worker_id, normalized_name = validate_worker_identity(worker_number, name)
    normalized_age, normalized_weight, normalized_sex = validate_profile(age, weight, sex)
    normalized_heart_rate, normalized_wbgt = validate_measurement(heart_rate, wbgt)
    (
        normalized_worker_status,
        normalized_heat_exposure_days,
        normalized_absence_days,
        normalized_similar_heat_work,
    ) = validate_acclimatization_inputs(
        worker_status,
        heat_exposure_days,
        absence_days,
        similar_heat_work,
    )
    return {
        "worker_id": worker_id,
        "worker_number": worker_id,
        "name": normalized_name,
        "age": normalized_age,
        "weight": normalized_weight,
        "sex": normalized_sex,
        "worker_status": normalized_worker_status,
        "heat_exposure_days": normalized_heat_exposure_days,
        "absence_days": normalized_absence_days,
        "similar_heat_work": normalized_similar_heat_work,
        "heart_rate": normalized_heart_rate,
        "wbgt": normalized_wbgt,
    }


def upsert_worker(
    worker_number,
    name,
    age=DEFAULT_PROFILE["age"],
    weight=DEFAULT_PROFILE["weight"],
    sex=DEFAULT_PROFILE["sex"],
    worker_status=DEFAULT_ACCLIMATIZATION["worker_status"],
    heat_exposure_days=DEFAULT_ACCLIMATIZATION["heat_exposure_days"],
    absence_days=DEFAULT_ACCLIMATIZATION["absence_days"],
    similar_heat_work=DEFAULT_ACCLIMATIZATION["similar_heat_work"],
    heart_rate=130,
    wbgt=31.2,
    path=WORKERS_PATH,
    updated_at=None,
):
    payload = validate_worker_payload(
        worker_number=worker_number,
        name=name,
        age=age,
        weight=weight,
        sex=sex,
        worker_status=worker_status,
        heat_exposure_days=heat_exposure_days,
        absence_days=absence_days,
        similar_heat_work=similar_heat_work,
        heart_rate=heart_rate,
        wbgt=wbgt,
    )
    workers = read_workers(path)
    timestamp = updated_at or now_iso()
    existing = workers.get(payload["worker_id"], {})
    payload["created_at"] = existing.get("created_at", timestamp)
    payload["updated_at"] = timestamp
    workers[payload["worker_id"]] = payload
    write_workers(workers, path)
    return payload


def worker_list(path=WORKERS_PATH):
    workers = read_workers(path)
    return sorted(workers.values(), key=lambda item: item.get("worker_number", ""))


def read_risk_events(path=RISK_EVENTS_PATH):
    events = read_json(path, [])
    if not isinstance(events, list):
        return []
    return events


def write_risk_events(events, path=RISK_EVENTS_PATH):
    atomic_write_json(path, events)


def append_risk_event(worker, values, path=RISK_EVENTS_PATH):
    risk = values["risk"]
    if risk not in ALERT_EVENT_LEVELS:
        return None

    event_time = now_iso()
    event = {
        "event_id": uuid.uuid4().hex,
        "event_time": event_time,
        "worker_id": worker["worker_id"],
        "worker_number": worker["worker_number"],
        "name": worker["name"],
        "risk": risk,
        "heart_rate": values["heart_rate"],
        "wbgt": values["wbgt"],
        "kcal": round(values["kcal"], 2),
        "metabolic_watts": round(values["metabolic_watts"], 1),
        "workload": values["workload"],
        "limit_wbgt": round(values["limit_wbgt"], 1),
        "margin": round(values["margin"], 1),
        "limit_type": values["limit_type"],
        "acclimatization": values["acclimatization"]["status_label"],
    }
    events = read_risk_events(path)
    events.append(event)
    write_risk_events(events, path)
    return event
