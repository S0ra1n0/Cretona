# Cretona Development Plan

## Project Overview

**Cretona** is a native Android application built with **Kotlin** that
allows users to generate AI videos from text prompts, images, or both
through third-party AI video generation APIs. The application includes
authentication, role-based access control, project history, and media
management.

## Tech Stack

-   **Platform:** Android (Native)
-   **Language:** Kotlin
-   **Architecture:** MVVM + Repository Pattern
-   **UI:** Jetpack Compose
-   **Networking:** Retrofit + OkHttp
-   **Backend:** Node.js + Express
-   **Database:** Supabase (PostgreSQL)
-   **Authentication:** Supabase Auth
-   **Storage:** Supabase Storage
-   **ORM:** Prisma
-   **AI Providers:** Runway, Kling, Pika, Luma, Google Veo (pluggable)

## MVP Features

### User

-   Register/Login
-   Manage profile
-   Generate AI video from text
-   Generate AI video from image
-   Generate AI video from text + image
-   View generation history
-   Download generated videos

### Admin

-   Manage users
-   View generation statistics
-   Disable user accounts

## Database

### roles(id,name)

### users(id UUID, role_id, username, email, created_at, updated_at)

### video_projects(id UUID,user_id,title,prompt,image_url,video_url,status,created_at,updated_at)

Status: pending, generating, completed, failed \###
generation_logs(id,project_id,provider,request_id,response,created_at)

Relationships: - Role 1:N Users - User 1:N VideoProjects - VideoProject
1:N GenerationLogs

## Development Roadmap

1.  Create Supabase project.
2.  Design PostgreSQL schema.
3.  Configure Supabase Auth and Storage.
4.  Build Express backend and Prisma.
5.  Implement authentication and RBAC.
6.  Create CRUD APIs for video projects.
7.  Develop Android app with Kotlin and Jetpack Compose.
8.  Integrate AI providers.
9.  Implement async job polling/webhooks.
10. Testing and production deployment.

## Backend Structure

``` text
src/
  controllers/
  routes/
  middleware/
  services/
    ai/
  prisma/
  utils/
```

## AI Flow

User -\> Android App -\> Backend -\> AI Provider -\> Job ID -\>
Poll/Webhook -\> Save video URL -\> Return result
