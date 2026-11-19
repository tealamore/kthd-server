# KTHD Backend API Contract

This document specifies the expected HTTP endpoints, request/response JSON schemas, HTTP verbs, headers, and status codes for the KTHD Android application backend integration.

---

## Global Request Headers

All HTTP requests sent by the mobile app automatically include the following HTTP headers via OkHttp interceptor:

| Header Name | Type | Example | Description |
| :--- | :--- | :--- | :--- |
| `Content-Type` | `string` | `application/json` | Standard JSON payload format |
| `X-Device-ID` | `string` | `8f3a21b4c5e67890` | Participant's unique 64-bit Android ID |
| `Idempotency-Key` | `string` | `3f1c9a7e-2b4d-4e8a-9c6f-0d5b7a1e2f34` | UUID generated once per request and reused on every retry of that request. See *Delivery & Retry Semantics*. |

---

## Endpoints Summary

| Endpoint Path | HTTP Verb | Purpose | Request Model | Response Model |
| :--- | :--- | :--- | :--- | :--- |
| `/context` | `POST` | Log app usage threshold events during an active task | `ContextPayload` | `ContextResponse` |
| `/consent` | `POST` | Record participant informed consent agreement | `ConsentPayload` | `ConsentResponse` |
| `/reward` | `POST` | Report reward observation data 5 minutes after intervention opportunity | `RewardPayload` | `RewardResponse` |
| `/participant/delete` | `POST` | Request deletion of all backend data for a participant ID | `DeleteParticipantPayload` | `DeleteParticipantResponse` |
| `/error` | `POST` | Report a non-2xx response the app received, so developers can be alerted | `ErrorReportPayload` | `ErrorReportResponse` |

---

## Delivery & Retry Semantics

The app persists every request in a local queue before sending it, so requests survive being offline and the app being closed.

* **Order**: requests are sent strictly in the order they were created. A request is never sent before an older one (e.g. a `/reward` is never sent before its `/context`; a new `/consent` is never sent before a pending `/participant/delete`).
* **Retried**: network failures, timeouts, `5xx`, `408` and `429`. Retried with exponential backoff, in the background, until accepted. While the oldest request is being retried, newer requests wait behind it.
* **Not retried**: any other non-`2xx` response (e.g. `400`). The request is dropped and reported to `/error`.
* **Deletion first**: a participant data deletion wipes every request still queued on the device, so `/participant/delete` is sent immediately and is never held up by older requests that are failing.
* **Duplicates**: the app never sends a request again once it has received a `2xx` for it. A request whose response was lost (e.g. a timeout after the server processed it) is retried with the **same** `Idempotency-Key`. The backend should store processed keys and, when a key is seen again, return the original response (`2xx`) without processing the request a second time. Different requests never share a key.

---

## Endpoint Specifications

### 1. Log Context Usage Event

Triggered periodically when a participant reaches the continuous app usage threshold (e.g. 60s) during an active task session.

* **HTTP Verb**: `POST`
* **Path**: `/context`

#### Request Body (`application/json`)
```json
{
  "id": 1,
  "task_id": 101,
  "device_id": "8f3a21b4c5e67890",
  "app_type": "Social",
  "continuous_duration": 60,
  "switch_count": 3,
  "timestamp": 1700000000000,
  "sync_status": "PENDING"
}
```

#### Request Schema
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `id` | `number` (Long) | Yes | Local database primary key ID |
| `task_id` | `number` (Long) | Yes | Identifier of the active task |
| `device_id` | `string` | Yes | Unique Participant Android ID |
| `app_type` | `string` | Yes | Name or category of foreground app (e.g. `"Social"`, `"Games"`) |
| `continuous_duration` | `number` (Long) | Yes | Continuous usage duration in seconds |
| `switch_count` | `number` (Int) | Yes | Total count of app switches during active task session |
| `timestamp` | `number` (Long) | Yes | Epoch timestamp in milliseconds when payload was recorded |
| `sync_status` | `string` | Yes | Local sync state (`"PENDING"`, `"SYNCED"`, or `"FAILED"`) |

#### Response Body (`200 OK`)
```json
{
  "notify": true
}
```

#### Response Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `notify` | `boolean` | If `true`, the mobile client triggers an alert notification to notify the participant. |

#### HTTP Status Codes
| Code | Reason | Description |
| :--- | :--- | :--- |
| `200 OK` | Success | Payload processed successfully. |
| `400 Bad Request` | Client Error | Malformed JSON or invalid data types. |
| `500 Internal Server Error` | Server Error | Backend server encountered an error processing the payload. |

---

### 2. Record Informed Consent

Triggered when the participant accepts the Informed Consent agreement upon first opening the app, or during background retries if offline.

* **HTTP Verb**: `POST`
* **Path**: `/consent`

#### Request Body (`application/json`)
```json
{
  "device_id": "8f3a21b4c5e67890",
  "consented": true,
  "consent_time_utc": "2026-10-21T12:00:00Z"
}
```

#### Request Schema
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `device_id` | `string` | Yes | Unique Participant Android ID |
| `consented` | `boolean` | Yes | Consent status (`true`) |
| `consent_time_utc` | `string` | Yes | Timestamp formatted in ISO 8601 UTC format |

#### Response Body (`200 OK`)
```json
{
  "success": true
}
```

#### Response Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | `boolean` | Indicates successful registration of consent record. |

#### HTTP Status Codes
| Code | Reason | Description |
| :--- | :--- | :--- |
| `200 OK` / `201 Created` | Success | Consent record registered successfully. |
| `400 Bad Request` | Client Error | Missing required fields or invalid timestamp. |
| `500 Internal Server Error` | Server Error | Backend database or server error while persisting consent. |

---

### 3. Report Reward Information

Triggered automatically 5 minutes (300 seconds) after receiving a successful response from an intervention opportunity (`POST /context`).

* **HTTP Verb**: `POST`
* **Path**: `/reward`

#### Request Body (`application/json`)
```json
{
  "device_id": "8f3a21b4c5e67890",
  "context_id": 1,
  "task_id": 101,
  "screen_locked": true,
  "app_closed": true,
  "time_to_close": 45
}
```

#### Request Schema
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `device_id` | `string` | Yes | Unique Participant Android ID |
| `context_id` | `number` (Long) | Yes | Associated context payload ID |
| `task_id` | `number` (Long) | Yes | Associated task ID |
| `screen_locked` | `boolean` | Yes | `true` if screen was locked or turned off at any point during the 5-minute window |
| `app_closed` | `boolean` | Yes | `true` if target app was closed/backgrounded at any point during the 5-minute window |
| `time_to_close` | `number` (Int) | Yes | Seconds (0 to 300) it took to close the target app; defaults to 300 if not closed |

#### Response Body (`200 OK`)
```json
{
  "success": true
}
```

#### Response Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | `boolean` | Indicates successful receipt of reward observation data. |

#### HTTP Status Codes
| Code | Reason | Description |
| :--- | :--- | :--- |
| `200 OK` | Success | Reward observation recorded successfully. |
| `400 Bad Request` | Client Error | Missing or invalid reward fields. |
| `500 Internal Server Error` | Server Error | Server error processing reward observation. |

---

### 4. Delete Participant Data

Triggered when the participant confirms data deletion from the Settings screen. At the same time the app withdraws consent, stops data collection, cancels any requests still queued, and erases study data on the device. No further data is sent for this device until a new `/consent` (which is always sent after the deletion request).

* **HTTP Verb**: `POST`
* **Path**: `/participant/delete`

#### Request Body (`application/json`)
```json
{
  "device_id": "8f3a21b4c5e67890"
}
```

#### Request Schema
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `device_id` | `string` | Yes | Unique Participant Android ID to delete |

#### Response Body (`200 OK`)
```json
{
  "success": true
}
```

#### Response Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | `boolean` | Indicates successful processing of data deletion request. |

#### HTTP Status Codes
| Code | Reason | Description |
| :--- | :--- | :--- |
| `200 OK` | Success | Participant data deletion request processed. |
| `400 Bad Request` | Client Error | Missing or invalid `device_id`. |
| `500 Internal Server Error` | Server Error | Backend failure during data deletion. |

---

### 5. Report Error

Sent automatically when another request receives a non-`2xx` response:

* every non-retryable response (e.g. `4xx`): the original request is dropped;
* the first retryable response (`5xx`, `408`, `429`) for a given request; later retries of the same request are not reported again.

Network failures and timeouts have no response and are not reported. Failures of `/error` itself are never reported. Error reports are queued and retried like any other request.

* **HTTP Verb**: `POST`
* **Path**: `/error`

#### Request Body (`application/json`)
```json
{
  "device_id": "8f3a21b4c5e67890",
  "request_type": "REWARD",
  "endpoint": "POST /reward",
  "idempotency_key": "3f1c9a7e-2b4d-4e8a-9c6f-0d5b7a1e2f34",
  "http_status": 400,
  "error_type": "HttpException",
  "error_message": "HTTP 400 Bad Request",
  "response_body": "{\"error\": \"context_id not found\"}",
  "request_body": "{\"device_id\":\"8f3a21b4c5e67890\",\"context_id\":42,...}",
  "attempts": 1,
  "will_retry": false,
  "occurred_at_utc": "2026-11-18T15:00:00Z"
}
```

#### Request Schema
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `device_id` | `string` | Yes | Unique Participant Android ID |
| `request_type` | `string` | Yes | One of `CONSENT`, `CONTEXT`, `REWARD`, `DELETE_PARTICIPANT` |
| `endpoint` | `string` | Yes | HTTP verb and path of the failed request, e.g. `POST /reward` |
| `idempotency_key` | `string` | Yes | `Idempotency-Key` of the failed request (the error report itself is sent with its own key) |
| `http_status` | `integer` | No | HTTP status code received (`null` if the failure was not an HTTP response, e.g. an unparseable body) |
| `error_type` | `string` | Yes | Client-side exception class name |
| `error_message` | `string` | No | Client-side exception message |
| `response_body` | `string` | No | Response body received, truncated to 2000 characters |
| `request_body` | `string` | Yes | JSON body of the failed request |
| `attempts` | `integer` | Yes | Number of times the request has been attempted, including this one |
| `will_retry` | `boolean` | Yes | Whether the app will retry the original request |
| `occurred_at_utc` | `string` | Yes | ISO-8601 UTC timestamp of the failure |

#### Response Body (`200 OK`)
```json
{
  "success": true
}
```

#### HTTP Status Codes
| Code | Reason | Description |
| :--- | :--- | :--- |
| `200 OK` | Success | Error report recorded. |
| `400 Bad Request` | Client Error | Malformed error report (dropped by the app, not retried). |
| `500 Internal Server Error` | Server Error | Backend failure; the app retries. |
