"""
tests/test_notifications.py — Mixtape

Tests for notification creation.
"""

import pytest
from app import create_app, db
from models import User, Song, Notification
from services.notification_service import rate_song


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


def test_rating_friends_song_notifies_original_sharer(app):
    """Rating a song shared by someone else creates a notification for the sharer."""
    with app.app_context():
        sharer = User(username="sharer", email="sharer@example.com")
        rater = User(username="rater", email="rater@example.com")
        db.session.add_all([sharer, rater])
        db.session.flush()

        song = Song(title="Rate Me", artist="The Bugs", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()

        rate_song(rater.id, song.id, 5)

        notifications = db.session.query(Notification).filter_by(user_id=sharer.id).all()
        assert len(notifications) == 1
        assert notifications[0].notification_type == "song_rated"
        assert "rater rated your song 'Rate Me' 5/5." == notifications[0].body


def test_rating_own_song_does_not_notify_self(app):
    """Users should not receive notifications for rating their own songs."""
    with app.app_context():
        user = User(username="owner", email="owner@example.com")
        db.session.add(user)
        db.session.flush()

        song = Song(title="My Song", artist="Solo", shared_by=user.id)
        db.session.add(song)
        db.session.commit()

        rate_song(user.id, song.id, 4)

        count = db.session.query(Notification).filter_by(user_id=user.id).count()
        assert count == 0
