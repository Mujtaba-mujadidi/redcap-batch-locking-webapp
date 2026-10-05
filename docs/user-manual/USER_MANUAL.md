# REDCap Batch Locking — User Manual

**Audience:** Oxford Vaccine Group data managers and study teams  
**Product:** Desktop app for batch lock / unlock of REDCap forms  
**Version:** 0.1.0 (pilot)

---

## Screenshots

Yes — screenshots can be added. This manual is written with image placeholders so you can drop PNGs into `docs/user-manual/images/` and they will render in Markdown preview / PDF export.

Suggested captures (macOS: `Cmd+Shift+4`, then Space, click the app window):

| File | Capture |
| --- | --- |
| `images/01-jobs.png` | Jobs page (main screen) |
| `images/02-import.png` | Import Request panel open |
| `images/03-mappings.png` | Mappings review |
| `images/04-processing.png` | Job running with progress |
| `images/05-reports.png` | Reports tab with Export |

Until those files exist, the image links below will appear broken in preview — that is expected.

---

## 1. What this app does

REDCap Batch Locking lets you:

1. Import a CSV of records/forms to **lock** or **unlock**
2. Confirm which REDCap fields drive form-complete / lock status / lock date
3. Run the batch against your REDCap project
4. Export a CSV report of what happened to each row

The app runs **on your computer**. Processing only continues while the app stays open. If you quit mid-job, you can reopen and resume remaining rows.

---

## 2. Install and open (Mac)

1. Open the DMG or unzip the app package you were given.
2. Drag **REDCap Batch Locking** into **Applications** (recommended).
3. Open the app from Applications (or from the folder you were sent).

### If macOS blocks the app

Unsigned pilot builds may show a security warning:

1. In Finder, **right-click** (or Control-click) the app
2. Choose **Open**
3. Confirm **Open** in the dialog

You only need to do this the first time.

### First launch

The window may take a few seconds while the local services start. If it stays on a starting screen, quit any other copy of the app and reopen once.

![Jobs page](images/01-jobs.png)

---

## 3. What you need before you start

From the Oxford Vaccine Group Development team (or your study’s REDCap admin):

- The **approved REDCap API URL** for your project host  
  *(Do not invent a URL. Unapproved URLs are blocked.)*
- A **REDCap API token** with permission to use the API on that project
- Confirmation that the **locking API** external module is enabled for the project

Also prepare:

- Your request CSV (or download the template from the app)
- Optionally, an unresolved-queries export if locks must be blocked when queries remain open

---

## 4. Prepare the request CSV

On the **Jobs** page:

1. Click **Export Template**
2. Save the CSV and fill it in

### Required columns

| Column | Meaning |
| --- | --- |
| `record_id` | REDCap record ID |
| `target_instrument` | Form / instrument unique name |
| `action` | `lock` or `unlock` |

### Optional columns

| Column | When to use |
| --- | --- |
| `event_name` | Longitudinal projects |
| `repeat_instance` | Repeating instruments |
| `arm_name` | Multi-arm projects |

Tips:

- Use the instrument’s **unique name**, not only the display label
- Keep files under **2 MB**
- One row = one form action for one record (and event/instance if needed)

---

## 5. Import a request

1. Open **Jobs**
2. Click **Import File**
3. Enter:
   - **API URL** (exactly the one provided by OVG Development)
   - **API Key** (project token)
4. Choose your request CSV
5. Optionally attach a queries CSV
6. Click **Run Import**

![Import panel](images/02-import.png)

### If the URL is not approved

You will see an alert asking you to contact the **Development team at the Oxford Vaccine Group**. Use only the URL you were given.

### If REDCap rejects the token

Typical messages:

- permissions / API access denied → token lacks API rights
- locking API not available → module not enabled on the project

Fix the token or project setup, then import again.

### After a successful import

- You may be taken to **Mappings** if forms need field confirmation
- Or the job may be ready to **Process** immediately if mappings already exist

---

## 6. Confirm mappings

On **Mappings**:

1. Review suggested fields for form complete / lock status / lock date
2. Correct any fields that need review
3. Confirm to save

If the project already has saved mappings, you may be asked to:

- **Use Existing Mappings**, or
- **Refresh Mappings** from live REDCap metadata

![Mappings](images/03-mappings.png)

---

## 7. Process a job

On **Jobs**, open the job actions menu and choose **Process** (or **Resume Remaining Rows** / **Retry Failed Rows** when shown).

1. Enter the API key if prompted  
   *(The app may remember it for about 2 hours for the same REDCap host in this session.)*
2. Watch progress on the Jobs page
3. **Keep the app open** until the job finishes

![Processing](images/04-processing.png)

### During processing

- Progress updates automatically
- Rate-limit waits may pause briefly (normal)
- You can **Cancel** a running/queued job from the actions menu

### After closing the app mid-job

1. Reopen the app
2. Find the interrupted job
3. Use **Resume Remaining Rows** (or retry failed rows if offered)
4. Re-enter the API key if the cached key expired

---

## 8. Export reports

### From Jobs

For a finished job, use **Export Report** in the actions menu and choose where to save the CSV.

### From Reports

1. Open the **Reports** tab
2. Find the file
3. Choose **Export** and save

![Reports](images/05-reports.png)

### How to read outcomes

| Outcome | Meaning |
| --- | --- |
| Locked / Unlocked | Action applied |
| Skipped | e.g. form not complete for a lock, or already in desired state |
| Blocked | e.g. unresolved query prevented a lock |
| Failed | Error for that row — see report detail |

The Jobs page focuses on your **latest requests**. Older exports remain under **Reports**.

---

## 9. Good practice

- Process against the correct project and token every time
- Prefer a short pilot on staging before large production runs
- Do not quit during active processing unless you intend to resume later
- Keep your API token private (treat it like a password)
- Contact OVG Development before using a new REDCap host

---

## 10. Troubleshooting

| Problem | What to try |
| --- | --- |
| App won’t open (Gatekeeper) | Right-click → Open |
| Stuck on starting / blank window | Quit all copies, reopen once |
| “URL not approved” | Use the URL from OVG Development |
| REDCap permissions error | Check API token rights on the project |
| Locking API error | Ask REDCap admin to enable locking API module |
| Export fails | Reopen the app and retry; confirm you have disk permission to save |
| Job interrupted | Reopen → Resume Remaining Rows |

### Support files (if Development asks)

- App data (Mac): `~/Library/Application Support/REDCap Batch Locking/`
- Logs (Mac): `~/Library/Logs/uk.ac.oxford.redcap.batchlocking/`

---

## 11. Support

For approved API URLs, new hosts, tokens, or locking-module setup, contact the **Development team at the Oxford Vaccine Group**.

---

## Appendix A — Adding screenshots to this manual

1. Open the app and navigate to the screen you want.
2. Press `Cmd+Shift+4`, then `Space`, then click the app window.
3. Move/rename the file into `docs/user-manual/images/` using the names in the table at the top.
4. Re-open this Markdown file — images should appear under each section.

To share as PDF: open this file in a Markdown preview that supports export (VS Code / Cursor / Typora / Pandoc), with the `images/` folder beside the document.
