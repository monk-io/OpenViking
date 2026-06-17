"""Tests for LoCoMo benchmark progress utilities."""

from rich.progress import ProgressColumn

from benchmark.locomo.vikingbot.progress_utils import (
    AsyncProgressTracker,
    ThreadSafeProgressTracker,
    ThreeStateBarColumn,
    make_three_state_progress,
)


def test_three_state_bar_column_initializes_progress_column_state():
    column = ThreeStateBarColumn()

    assert isinstance(column, ProgressColumn)
    assert hasattr(column, "_renderable_cache")
    assert hasattr(column, "_update_time")


def test_three_state_progress_renders_without_missing_cache_error():
    progress, task_id = make_three_state_progress(description="Test", transient=True)
    progress.update(task_id, total=4, completed=2, running=1, succeeded=1, failed=1)

    renderables = list(progress.get_renderables())

    assert renderables


def test_locomo_progress_tracker_records_failed_jobs():
    progress, task_id = make_three_state_progress(description="Test", transient=True)
    tracker = ThreadSafeProgressTracker(progress, task_id, total=2)

    tracker.job_started()
    tracker.job_finished()
    tracker.job_started()
    tracker.job_finished(failed=True)

    task = progress.tasks[0]
    assert tracker.done == 2
    assert tracker.failed == 1
    assert task.completed == 2
    assert task.fields["succeeded"] == 1
    assert task.fields["failed"] == 1


def test_async_progress_tracker_records_failed_jobs():
    progress, task_id = make_three_state_progress(description="Test", transient=True)
    tracker = AsyncProgressTracker(progress, task_id, total=2)

    tracker.job_started()
    tracker.job_finished(failed=True)

    task = progress.tasks[0]
    assert tracker.done == 1
    assert tracker.failed == 1
    assert task.completed == 1
    assert task.fields["succeeded"] == 0
    assert task.fields["failed"] == 1
