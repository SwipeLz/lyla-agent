# MVP Scope

## Included in MVP
- FastAPI backend skeleton
- SQLite database schema and persistence
- Google ADK agent runtime for processing text commands
- Core tool implementations for tasks, expenses, and summaries
- Text-based API endpoints for agent interaction
- Device command polling endpoint (stubbed for hardware)

## Not Included in MVP
- Audio processing (STT/TTS)
- ESP32 firmware and hardware prototype
- Web dashboard frontend
- WhatsApp integration
- PostgreSQL database

## MVP Success Criteria
- The backend successfully receives text commands via API.
- The Google ADK agent interprets commands accurately.
- Tasks, expenses, and reminders are correctly saved to the SQLite database.
- The agent provides concise, accurate responses based on the database state.

## Main User Scenarios

### a. Create Academic Task
**User:** "Tolong ingatkan besok ada tugas Matkul Jaringan jam 10 pagi."
**Agent:** Extracts task details, saves to database, and confirms.

### b. Create Expense
**User:** "Tadi aku beli makan siang 25 ribu."
**Agent:** Extracts expense amount and category, saves to database, and confirms.

### c. Create Reminder
**User:** "Ingatkan aku untuk bayar kos tanggal 1."
**Agent:** Creates a general reminder, saves to database, and confirms.

### d. Combined Command: Expense + Reminder
**User:** "Aku baru beli buku 50 ribu, ingatkan besok baca bab 1 ya."
**Agent:** Processes both actions sequentially (creates expense, creates reminder), and provides a combined confirmation.

### e. Ask Today Summary
**User:** "Hari ini ada apa aja?"
**Agent:** Retrieves tasks and expenses for today and generates a short summary.
