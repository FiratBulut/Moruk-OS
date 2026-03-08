from typing import Any
"""
Moruk OS - Task Management Plugin
Provides tools to list and delete tasks.
"""
from core.task_manager import TaskManager
from core.logger import get_logger
log = get_logger('plugin_tasks')
task_manager = TaskManager()
PLUGIN_CORE = True
PLUGIN_NAME = 'tasks'
PLUGIN_DESCRIPTION = 'Manage tasks: list, delete, clear.'
PLUGIN_PARAMS = '"action": "list|delete|clear_completed|clear_all", "task_id": "string (optional)"'

def execute(params: Any) -> Any:
    action = params.get('action', 'list')
    if action == 'list':
        tasks = task_manager.tasks
        if not tasks:
            return {'success': True, 'result': 'No tasks found.'}
        output = ['Current Tasks:']
        for t in tasks:
            status_icon = '✅' if t['status'] == 'completed' else '⏳'
            output.append(f'{status_icon} [{t['id']}] {t['title']} ({t['priority']}) - {t['status']}')
        return {'success': True, 'result': '\n'.join(output)}
    elif action == 'delete':
        task_id = params.get('task_id')
        if not task_id:
            return {'success': False, 'result': 'Missing task_id'}
        if task_manager.delete_task(task_id):
            return {'success': True, 'result': f'Task {task_id} deleted.'}
        else:
            return {'success': False, 'result': f'Task {task_id} not found.'}
    elif action == 'clear_completed':
        task_manager.clear_completed()
        return {'success': True, 'result': 'Completed tasks cleared.'}
    elif action == 'clear_all':
        task_manager.clear_all()
        return {'success': True, 'result': 'All tasks cleared.'}
    return {'success': False, 'result': f'Unknown action: {action}'}