# API Draft

> **Note:** This document outlines the proposed API endpoints. No implementation exists in Phase 0.

## GET /health
- **Purpose:** Health check endpoint to verify backend status.
- **Response Example:**
  ```json
  { "status": "ok", "timestamp": "2026-05-16T14:00:00Z" }
  ```
- **Notes:** Used by deployment monitors and the dashboard.

## POST /agent/text
- **Purpose:** Send a text command to the Google ADK agent.
- **Request Example:**
  ```json
  { "text": "Catat pengeluaran makan 20 ribu", "timezone": "Asia/Jakarta" }
  ```
- **Response Example:**
  ```json
  { "response": "Pengeluaran makan sebesar 20 ribu telah dicatat." }
  ```
- **Notes:** Main endpoint for the MVP.

## POST /agent/audio
- **Purpose:** (Later phase) Send an audio file/stream to be processed by STT, passed to the agent, and returned as TTS.
- **Notes:** Will accept `multipart/form-data`.

## GET /dashboard/tasks
- **Purpose:** Retrieve a list of academic tasks.
- **Response Example:**
  ```json
  [
    { "id": 1, "title": "Tugas Jaringan", "deadline": "2026-05-17T10:00:00Z", "status": "pending" }
  ]
  ```

## GET /dashboard/expenses
- **Purpose:** Retrieve a list of expenses.
- **Response Example:**
  ```json
  [
    { "id": 1, "category": "Makan", "amount": 20000, "date": "2026-05-16T12:30:00Z" }
  ]
  ```

## GET /dashboard/summary
- **Purpose:** Retrieve a summary of today's activities (tasks due, total expenses).
- **Response Example:**
  ```json
  { "tasks_due_today": 2, "total_expenses_today": 45000 }
  ```

## GET /devices/{device_code}/commands/pending
- **Purpose:** Long-polling or standard GET endpoint for the ESP32 to fetch pending commands (e.g., update face, play sound).
- **Response Example:**
  ```json
  [
    { "command_id": "cmd_123", "action": "update_face", "payload": "happy" }
  ]
  ```
- **Notes:** Required for ESP32 hardware integration.

## POST /devices/{device_code}/commands/{command_id}/ack
- **Purpose:** Endpoint for the ESP32 to acknowledge that a command was successfully executed.
- **Request Example:**
  ```json
  { "status": "completed" }
  ```
- **Response Example:**
  ```json
  { "success": true }
  ```
