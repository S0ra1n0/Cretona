# Cretona

Cretona is a native Android application that generates AI videos from text, images, or both using external AI APIs, with user authentication and role-based management.

## Repository layout

```text
Cretona/            ← open this folder in Android Studio
├── app/            Android application (Kotlin · Jetpack Compose · MVVM)
├── backend/        Express + Prisma service (not yet implemented)
├── docs/           requirements, API contract, data model, ADRs
└── gradle/         version catalog + wrapper
```

The repository root **is** the Gradle project, so Android Studio opens it directly. `backend/` and `docs/` are ignored by Gradle sync.

## Getting started

Prerequisites, `local.properties` keys, and build commands are in **[docs/SETUP.md](docs/SETUP.md)**.

```bash
./gradlew :app:assembleDebug
```

## Documentation

Start at **[docs/README.md](docs/README.md)**. The plan and current progress live in [Cretona_Roadmap.md](Cretona_Roadmap.md).

## Stack

Kotlin · Jetpack Compose · MVVM + Repository · Hilt · Retrofit/OkHttp · Media3 · Coil — talking to a Node.js/Express backend over Supabase (Postgres, Auth, Storage), which orchestrates pluggable third-party AI video providers.
