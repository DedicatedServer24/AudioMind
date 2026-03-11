# AudioMind – Deployment-Anleitung (Coolify)

## Voraussetzungen

- Coolify-Instanz mit Zugriff auf das GitHub-Repository
- OpenAI API Key

## Schritte

### 1. Coolify: Neuen Service anlegen

1. In Coolify: **New Resource** > **Application**
2. Source: **GitHub (Private Repository)** > Repository auswählen
3. Build Pack: **Dockerfile**
4. Port: **8501**

### 3. Environment Variables setzen

In Coolify unter **Environment Variables**:

| Variable | Wert |
|---|---|
| `OPENAI_API_KEY` | `sk-...` (dein API Key) |

### 4. Persistentes Volume für config.yaml

Damit User-Daten (Passwörter) ohne Rebuild geändert werden können.

**In Coolify einrichten:**

1. Application auswählen → **Storages** Tab (oder **Persistent Storage**)
2. **Add** klicken
3. Eingaben:
   - **Name:** `audiomind-config` (frei wählbar)
   - **Source Path (Host):** `/data/audiomind/config.yaml`
   - **Destination Path (Container):** `/app/config.yaml`
4. **Save**

**Zusätzlich: Persistentes Volume für die SQLite-Datenbank:**

1. **Add** klicken
2. Eingaben:
   - **Name:** `audiomind-data`
   - **Source Path (Host):** `/data/audiomind/data`
   - **Destination Path (Container):** `/app/data`
3. **Save**

> Die DB-Datei (`audiomind.db`) wird automatisch im `data/`-Verzeichnis erstellt. Das Verzeichnis auf dem Host wird beim ersten Start automatisch angelegt.

**config.yaml auf dem Server ablegen:**

Die Datei muss einmalig auf dem Coolify-Server erstellt werden:

```bash
# Per SSH auf den Coolify-Server verbinden
ssh user@dein-server

# Verzeichnis erstellen und config anlegen
mkdir -p /data/audiomind
nano /data/audiomind/config.yaml
```

Inhalt der `config.yaml` – siehe `audiomind-plan.md` (Abschnitt Authentifizierung) für das Format mit bcrypt-gehashten Passwörtern.

### 5. Domain & HTTPS

1. In Coolify unter **Settings** > **Domains**:
   - Domain eintragen, z.B. `audiomind.deinedomain.de`
2. HTTPS wird automatisch via Let's Encrypt aktiviert

### 6. Auto-Deploy bei GitHub Push (Webhook)

Coolify kann automatisch ein Redeploy auslösen, wenn du auf GitHub pushst:

1. Application auswählen → **General** Tab
2. **Auto Deploy** aktivieren (Webhook-basiert)
3. Coolify generiert eine **Webhook-URL** – diese wird automatisch im GitHub-Repo registriert, wenn Coolify Zugriff auf das Repo hat
4. Ab jetzt: jeder `git push` auf den konfigurierten Branch löst automatisch einen Build + Deploy aus

> **Hinweis:** Falls der Webhook nicht automatisch angelegt wird, kannst du ihn manuell in GitHub unter **Settings → Webhooks** eintragen. Die URL findest du in Coolify unter den Application-Settings.

### 7. Deploy (manuell)

- **Deploy** klicken
- Warten bis Build + Start abgeschlossen
- App ist erreichbar unter `https://audiomind.deinedomain.de`

## Lokaler Docker-Test

```bash
# Image bauen
docker build -t audiomind:latest .

# Container starten
docker run -d \
  --name audiomind \
  -p 8501:8501 \
  -e OPENAI_API_KEY=sk-dein-key \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/data:/app/data \
  audiomind:latest
```

App erreichbar unter: http://localhost:8501

## Nutzerverwaltung

### Wie funktioniert die Anmeldung?

AudioMind nutzt `streamlit-authenticator` mit einer `config.yaml` auf dem Server. Es gibt **keine Selbstregistrierung** – das ist ein bewusstes Design für ein internes Team-Tool.

| Rolle | Was sie tun | bcrypt nötig? |
|---|---|---|
| **Admin** | Nutzer anlegen (Hash generieren, config.yaml pflegen) | Ja, einmalig lokal |
| **Nutzer** | Login mit Username + Passwort im Browser | Nein |

**Flow:**
1. **Admin** generiert lokal einen bcrypt-Hash für das gewünschte Passwort
2. **Admin** trägt Username + Hash in die `config.yaml` auf dem Server ein
3. **Nutzer** öffnet die App im Browser und loggt sich mit Username + Klartext-Passwort ein
4. `streamlit-authenticator` vergleicht serverseitig das Passwort mit dem Hash – der Nutzer merkt davon nichts

### Neuen Nutzer anlegen (Admin)

**1. Passwort-Hash lokal generieren:**

```bash
# Im Projekt-Verzeichnis (mit aktiviertem .venv)
.venv/Scripts/python -c "import bcrypt; print(bcrypt.hashpw('dein-passwort'.encode(), bcrypt.gensalt()).decode())"
```

**2. Hash in config.yaml auf dem Server eintragen:**

```bash
ssh user@dein-server
nano /data/audiomind/config.yaml
```

Neuen User-Block hinzufügen:

```yaml
credentials:
  usernames:
    neuer.nutzer:
      name: Neuer Nutzer
      password: $2b$12$...  # den generierten Hash hier einfügen
```

Der neue Nutzer kann sich sofort einloggen – kein Redeploy nötig, da die `config.yaml` als Volume gemountet ist.

### Selbstregistrierung ermöglichen (optional, nicht in V1)

Falls Nutzer sich selbst registrieren können sollen, wäre folgendes nötig:

1. **Registrierungsformular** in der App (Username, Name, Passwort) – `streamlit-authenticator` bietet dafür ein fertiges Widget: `authenticator.register_user()`
2. **config.yaml schreibbar machen** – die App muss die `config.yaml` im Container ändern dürfen. Da sie als Volume gemountet ist, bleiben Änderungen persistent
3. **Sicherheitsüberlegungen:**
   - Einladungscode oder Admin-Freigabe, damit sich nicht jeder registrieren kann
   - Rate-Limiting gegen Spam-Registrierungen
   - Ggf. E-Mail-Verifizierung

**Aufwand:** gering (streamlit-authenticator bringt das meiste mit), aber erfordert Entscheidungen zur Zugangskontrolle.
