# Mixtape Submission

## AI Usage

I used AI as a debugging partner and writing assistant, but I treated its suggestions as hypotheses that had to be checked against the code and tests. The main workflow was: I read the route and service files first, reproduced the behavior with pytest or controlled in-memory data, then used AI help to explain suspicious code paths and sharpen the root cause wording.

For Issue #1, after tracing the listen route into `services/streak_service.py`, I used AI to sanity-check the date edge case and the meaning of Python's `datetime.weekday()`. The useful part was confirming that Sunday is represented as `6`, which made the condition `today.weekday() != 6` clearly suspicious. I still verified the diagnosis myself by running the Saturday-to-Sunday streak test before changing the code.

For Issue #4, I used AI to compare two similar code paths: `add_to_playlist()` and `rate_song()` in `services/notification_service.py`. That helped me describe the structural difference: playlist adds called `create_notification()` for `song.shared_by`, while ratings saved the `Rating` and returned without creating a notification. I verified this myself by creating two users and one song in an in-memory database, calling `rate_song()`, and checking that the sharer's notification count stayed at `0` before the fix.

For Issue #5, I used AI mostly to phrase the root cause clearly after I had already found the exact return expression. The important evidence came from reading `get_playlist_songs()` and seeing that the database query ordered the songs correctly, but the final Python slice `songs[:-1]` discarded the last item. I verified this with the playlist test fixture that created five positioned songs and got back only four.

One place where AI could have led me in the wrong direction was Issue #3, the search duplicate report. The starter test comments suggested a multi-tag song might duplicate, but when I ran the search tests they all passed, likely because SQLAlchemy returned unique `Song` entities for that query shape. Since I could not reproduce that reported behavior, I did not fix Issue #3 and instead chose Issue #4, which I could reproduce with controlled data. That was a useful reminder that AI explanations and code comments are not enough; the bug had to reproduce before I treated it as real.

## Codebase Map

### Main files and directories

`app.py` is the Flask application factory. It creates the Flask app, configures SQLAlchemy, initializes the shared `db` object, registers the route blueprints, and creates database tables inside the app context. The registered URL groups are `/songs`, `/playlists`, `/users`, and `/feed`.

`models.py` defines the database schema with SQLAlchemy. The main models are `User`, `Song`, `Tag`, `ListeningEvent`, `Rating`, `Playlist`, and `Notification`. It also defines association tables for many-to-many relationships: `friendships` connects users to their friends, `song_tags` connects songs to tags, and `playlist_entries` connects playlists to songs while storing extra playlist-specific data like `position`, `added_by`, and `added_at`.

`routes/` contains the HTTP API layer. These files parse request data, call service functions, convert returned models or dictionaries into JSON responses, and translate service errors into HTTP status codes.

`routes/songs.py` handles song search, song detail lookup, song ratings, and listening events. Its endpoints delegate to `search_service`, `notification_service`, and `streak_service`.

`routes/playlists.py` handles playlist creation, playlist metadata lookup, retrieving playlist songs, and adding songs to playlists. It mostly delegates to `playlist_service`, while adding a song to a playlist delegates to `notification_service.add_to_playlist()`.

`routes/users.py` handles user profile lookup, listening streak lookup, notification lookup, and marking notifications as read. Most user-related business behavior is delegated to services, though the basic user profile endpoint queries the `User` model directly.

`routes/feed.py` handles the social feed endpoints: friends listening now and general friend activity. Both endpoints delegate to `feed_service`.

`services/` contains the business logic. The README says the known bugs live in this layer, which matches the route pattern: routes are thin, while service functions decide how records are queried, created, updated, and returned.

`services/search_service.py` searches for songs and returns song dictionaries with tag data. It also contains `get_song()` for single-song lookup.

`services/playlist_service.py` creates playlists and retrieves playlist data. `get_playlist_songs()` queries through `playlist_entries` so songs can be returned in explicit playlist position order.

`services/notification_service.py` creates and retrieves notifications. It also contains behavior for rating songs and adding songs to playlists, because those user actions can create notifications for the original song sharer.

`services/streak_service.py` records listening events and updates a user's listening streak based on their previous listening date.

`services/feed_service.py` builds friend-based feeds from `ListeningEvent` records. One feed shows recent listening activity, while the activity feed returns the latest friend events up to a limit.

`seed_data.py` resets and populates the local SQLite database with users, friendships, songs, tags, listening events, playlists, and one example notification. The seed data is designed to expose the project issues, such as songs with multiple tags, recent versus older listening events, and ordered playlist entries.

`tests/` contains pytest tests for several service behaviors. The tests create in-memory SQLite databases, seed small focused datasets, call service functions directly, and assert expected behavior without needing to run the Flask server.

### Data model notes

Users are central to most features. A `User` can share songs, rate songs, listen to songs, receive notifications, create playlists, and have friends through the `friendships` association table.

Songs belong to the user who originally shared them through `Song.shared_by`. Songs can have many tags through `song_tags`, many ratings through `Rating`, and many listening events through `ListeningEvent`.

Playlists are created by a user, but songs are attached through `playlist_entries` instead of only through a plain relationship. That join table matters because playlist membership has extra information: the song's `position`, who added it, and when it was added.

Notifications are stored as their own records. They belong to a recipient user and include a short type string plus a human-readable body. Other services can create notifications when a user's shared song is acted on.

### Data flow example: adding a song to a playlist

The playlist add flow starts with `POST /playlists/<playlist_id>/songs` in `routes/playlists.py`.

The route reads JSON from the request body and expects `song_id` and `added_by`. If either value is missing, the route returns a `400` error before calling the service layer.

If the request has the required fields, the route calls `notification_service.add_to_playlist(playlist_id, song_id, added_by)`.

Inside `add_to_playlist()`, the service loads the `Song`, the user who added the song, and the `Playlist` from the database. If any of those records do not exist, the service raises a `ValueError`, and the route turns that into a `400` JSON error response.

If the records exist, the service appends the song to `playlist.songs` when it is not already in the playlist and commits the database change. The `Playlist.songs` relationship uses the `playlist_entries` association table, so the database stores playlist-song membership separately from the song itself.

After adding the song, the service checks whether the person adding the song is different from the song's original sharer. If so, it calls `create_notification()` to create a `Notification` for the original sharer with the type `song_added_to_playlist`.

The route then returns `{"message": "Song added to playlist"}` with status `201`.

### Organization patterns I noticed

The app uses an application factory pattern. Tests and the Flask command can call `create_app()` with different config values, which is why the tests can use an in-memory SQLite database.

The route layer is intentionally thin. Most routes validate required request fields, call exactly one service function, and format the result as JSON. This means bug investigation should usually trace from a route into the matching service file.

The service layer owns business rules and database writes. Examples include deciding when a listening streak increments, which listening events count as recent, whether adding a song should notify the original sharer, and how playlist songs are ordered.

Most model classes provide `to_dict()` methods. Services and routes rely on these methods to produce JSON-friendly responses instead of manually formatting every model in every route.

Errors are usually communicated from services to routes with `ValueError`. Routes catch those exceptions and convert them into JSON error responses with either `400` or `404` status codes depending on the endpoint.

The tests focus on service functions rather than HTTP endpoints. That matches the app's structure because the services contain the important behavior and the known bugs.

## Bug Fixes

### Issue #1: My listening streak keeps resetting

**Issue number and title:** Issue #1, "My listening streak keeps resetting"

**How I reproduced it:** I ran the existing streak tests with `.venv/bin/python -m pytest tests/test_streaks.py`. The failure was `test_streak_increments_on_sunday`: a user listened on Saturday, June 15, 2024 at 12:00 UTC and then Sunday, June 16, 2024 at 12:00 UTC. Because those are consecutive calendar days, the listening streak should have increased from `1` to `2`, but it stayed at `1`.

**How I found the root cause:** I started at the user-facing action, `POST /songs/<song_id>/listen` in `routes/songs.py`, and followed it to `record_listening_event()` in `services/streak_service.py`. That function creates a `ListeningEvent` and then calls `update_listening_streak(user, now)`, so I read that helper next. The moment that made the cause specific was the branch `elif days_since_last == 1 and today.weekday() != 6`: the failing test date was Sunday, and Python's `datetime.weekday()` returns `6` for Sunday, so that exact comparison excluded the only consecutive-day case being tested.

**Root cause:** `update_listening_streak()` calculated `days_since_last` correctly, but it only incremented a one-day streak when `today.weekday() != 6`. In Python, `datetime.weekday()` returns `6` for Sunday. That meant Saturday-to-Sunday listening had `days_since_last == 1` but failed the extra weekday check, so the code skipped the increment branch and fell into the reset branch.

**Your fix and side-effect check:** I removed only the Sunday exclusion, so any `days_since_last == 1` now increments the streak. I checked related streak behavior with `tests/test_streaks.py`: first listen still starts at `1`, same-day listening still does not double count, Monday-to-Tuesday still increments, skipped days still reset, and Saturday-to-Sunday now increments.

### Issue #4: Rating a friend's song does not create a notification

**Issue number and title:** Issue #4, "I got notified when a friend added my song to a playlist but not when they rated it"

**How I reproduced it:** I created an in-memory test app with two users: `sharer` and `rater`. `sharer` shared a song titled `Rate Me`, which made `sharer.id` the song's `shared_by` owner. Then I called `rate_song(rater.id, song.id, 5)`. Before the call, `sharer` had `0` notifications. After the call, `sharer` still had `0` notifications, even though playlist additions already notified the original sharer.

**How I found the root cause:** I started at `POST /songs/<song_id>/rate` in `routes/songs.py` and followed the route to `rate_song()` in `services/notification_service.py`. To compare the expected notification behavior, I read the nearby `add_to_playlist()` path in the same service and traced its call to `create_notification()`. The moment that made the cause specific was the structural difference between the two paths: `add_to_playlist()` explicitly checks `song.shared_by != added_by_user_id` and calls `create_notification()`, while `rate_song()` commits the `Rating` and returns without any equivalent notification call.

**Root cause:** `rate_song()` created or updated the `Rating` record but returned immediately after committing. The service already had a shared notification helper, `create_notification()`, and the playlist-add flow used it to notify `song.shared_by`, but the rating flow never called it. As a result, the rating was saved successfully while the original song sharer never received a `Notification` row.

**Your fix and side-effect check:** After saving the rating, `rate_song()` now creates a `song_rated` notification for the original sharer when the rater is someone else. I added focused regression tests for rating someone else's song and rating your own song, so the new behavior does not create self-notifications. I also checked the existing playlist notification path stayed unchanged.

### Issue #5: The last song in a playlist never shows up

**Issue number and title:** Issue #5, "The last song in a playlist never shows up"

**How I reproduced it:** I ran the existing playlist tests with `.venv/bin/python -m pytest tests/test_playlists.py`. The fixture creates a playlist with five songs at positions 1 through 5 in the `playlist_entries` join table. `get_playlist_songs()` returned only four songs: `Track 1` through `Track 4`, omitting `Track 5`.

**How I found the root cause:** I started at `GET /playlists/<playlist_id>/songs` in `routes/playlists.py` and followed it to `get_playlist_songs()` in `services/playlist_service.py`. I checked `models.py` to confirm playlist songs come through the `playlist_entries` association table with a `position` column. The query itself joined the right table, filtered by playlist ID, and ordered by position, so the moment that made the cause specific was the final return expression: it converted `songs[:-1]` instead of `songs`, dropping the last item after the database query had already returned the correct list.

**Root cause:** `get_playlist_songs()` queried the correct ordered song list from the database, but returned `[song.to_dict() for song in songs[:-1]]`. In Python, `songs[:-1]` means "all elements except the last one," so the service intentionally discarded the final song after retrieving it correctly.

**Your fix and side-effect check:** I returned all queried songs with `[song.to_dict() for song in songs]`. I checked the related playlist boundaries with `tests/test_playlists.py`: empty playlists still return `[]`, playlists return all songs, and the ordering by `playlist_entries.position` is preserved.

## Verification

After the fixes, I ran `.venv/bin/python -m pytest tests/`. All 15 tests passed.
