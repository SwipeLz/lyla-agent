# Roadmap

## Phase 0: Planning
- **Objective:** Establish project documentation, architecture, and configuration placeholders.
- **Main Steps:** Create README, architecture docs, scope, agent design, API draft, and database plan.
- **Milestone:** All planning documentation finalized.

## Phase 1: Backend Skeleton
- **Objective:** Setup FastAPI project structure.
- **Main Steps:** Initialize project, configure routers, setup dependency injection.
- **Milestone:** Basic API running and `/health` endpoint reachable.

## Phase 2: Database Schema
- **Objective:** Implement initial SQLite database.
- **Main Steps:** Setup SQLAlchemy, define models, configure Alembic for migrations.
- **Milestone:** Database models created and migrations working.

## Phase 3: Service Layer and Tools
- **Objective:** Build core business logic.
- **Main Steps:** Create services for managing tasks, expenses, and reminders.
- **Milestone:** CRUD operations verified via unit tests.

## Phase 4: Google ADK Agent Runtime
- **Objective:** Integrate Google ADK.
- **Main Steps:** Setup agent configuration, integrate tools from Phase 3, define system prompts.
- **Milestone:** Agent successfully processes static text commands via CLI/tests.

## Phase 5: Text Command Endpoint
- **Objective:** Expose agent functionality via REST API.
- **Main Steps:** Create `/agent/text` endpoint, wire it to the Google ADK runtime.
- **Milestone:** End-to-end text command processing via API.

## Phase 6: Scheduler
- **Objective:** Handle time-based events.
- **Main Steps:** Setup APScheduler or Celery for processing reminders and scheduled commands.
- **Milestone:** Background jobs running and logging correctly.

## Phase 7: Device Command Queue
- **Objective:** Enable backend-to-device communication.
- **Main Steps:** Create command tables, implement polling and acknowledgment endpoints.
- **Milestone:** `/devices/{device_code}/commands/pending` returns queued commands.

## Phase 8: Dashboard API (Current)
- **Objective:** Expose data for the frontend dashboard.
- **Main Steps:** Create read-only endpoints for tasks, expenses, and summaries.
- **Milestone:** Dashboard API fully functional.

## Phase 9: Dashboard Frontend
- **Objective:** Build the web dashboard.
- **Main Steps:** Create frontend application to consume Dashboard APIs.
- **Milestone:** User can view tasks and expenses on the web.

## Phase 10: Audio Backend
- **Objective:** Add voice processing capabilities.
- **Main Steps:** Integrate STT (Speech-to-Text) and TTS (Text-to-Speech) services, create `/agent/audio` endpoint.
- **Milestone:** Backend can receive audio, process it, and return audio responses.

## Phase 11: ESP Prototype
- **Objective:** Initial hardware setup.
- **Main Steps:** Flash ESP32-S3, setup WiFi, implement device command polling.
- **Milestone:** ESP32 successfully polls and acknowledges commands from the backend.

## Phase 12: ESP Audio Integration
- **Objective:** Enable voice interaction on the device.
- **Main Steps:** Implement audio recording, streaming to backend, and playing TTS responses.
- **Milestone:** End-to-end voice interaction through the ESP32.

## Phase 13: WhatsApp Notification
- **Objective:** Add external notification channels.
- **Main Steps:** Integrate WhatsApp Business API for reminders and daily summaries.
- **Milestone:** User receives automated reminders on WhatsApp.

## Phase 14: Testing and Demo
- **Objective:** Finalize project for presentation.
- **Main Steps:** Comprehensive testing, bug fixing, demo preparation.
- **Milestone:** Project ready for deployment and showcase.
