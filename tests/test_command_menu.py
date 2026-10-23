from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from bot_dock.app import create_app
from bot_dock.config import Route, Settings


@pytest.mark.parametrize('routes, expected', [
    ([{'command': '/status', 'description': '查詢狀態', 'aliases': ['/state']},
      {'command': '/help'}], [('status', '查詢狀態'), ('help', '/help')]),
    ([], []),
])
def test_startup_syncs_only_receiving_bot_menu(monkeypatch, routes, expected):
    monkeypatch.setenv('KEY', 'test-key')
    settings = Settings.model_validate({
        'projects': {'demo': {'api_key_env': 'KEY', 'callback_url': 'http://project/query',
                             'callback_key_env': 'KEY', 'routes': routes}},
        'bots': {name: {'token_env': 'UNUSED', 'project_id': 'demo',
                       'receive_updates': receiving, 'destinations': {'owner': 42},
                       'allowed_chat_ids': [42]}
                 for name, receiving in [('interactive', True), ('notify', False)]},
    })
    bots = {name: SimpleNamespace(token=name, get_me=AsyncMock(),
                                 get_webhook_info=AsyncMock(return_value=SimpleNamespace(url='')),
                                 set_my_commands=AsyncMock())
            for name in settings.bots}
    app = create_app(settings, bots=bots)
    with patch.object(app.state.dispatcher, 'start_polling', new=AsyncMock()):
        with TestClient(app):
            bots['interactive'].set_my_commands.assert_awaited_once()
            commands = bots['interactive'].set_my_commands.call_args.args[0]
            assert [(item.command, item.description) for item in commands] == expected
            bots['notify'].set_my_commands.assert_not_awaited()


@pytest.mark.parametrize('route', [
    {'command': '/UPPER'}, {'command': '/has-dash'}, {'command': 'status'},
    {'command': '/' + 'a' * 33}, {'command': '/ok', 'description': ''},
    {'command': '/ok', 'description': 'x' * 257},
])
def test_invalid_menu_entries_rejected(route):
    with pytest.raises(ValidationError):
        Route.model_validate(route)
