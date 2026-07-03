# Mixtape Submission

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
