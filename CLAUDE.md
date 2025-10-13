# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## High-level Architecture

This project is a plugin for AstrBot that allows creating and managing dynamic interactive buttons and menus within Telegram. The core functionality is divided into several key components:

1.  **Plugin Core (`main.py`)**: The `DynamicButtonFrameworkPlugin` class is the main entry point. It handles the plugin lifecycle, registers commands (e.g., `/menu`), and integrates all other components.

2.  **Data Storage (`storage.py`)**: The plugin's state, including button layouts, menu structures, action definitions, and workflows, is stored in a single JSON file (`data/plugins/astrbot_plugin_tg_button/buttons_state.json`). The `ButtonStore` class manages reading from and writing to this file.

3.  **Telegram Interaction (`handlers.py`)**: This module is the router for user interactions. It processes callback queries from Telegram when a user clicks an inline button and dispatches the request to the appropriate logic based on the callback data.

4.  **Execution Engine (`actions.py`)**: The `ActionExecutor` is the heart of the plugin's logic. It can execute three types of operations:
    *   **HTTP Actions**: Make external web requests. They use Jinja2 templates for dynamic URLs, headers, and bodies, and can parse JSON responses.
    *   **Local/Modular Actions**: Execute Python code. "Local" actions are registered directly via the plugin's internal API, while "Modular" actions are loaded from individual `.py` files in a dedicated directory, making them extensible by the user.
    *   **Workflows**: Execute a directed acyclic graph (DAG) of other actions. This allows for creating complex, multi-step processes by chaining actions together, where the output of one action can be the input for another.

5.  **Web UI (`webui.py`)**: An `aiohttp`-based web server that provides a graphical interface and a REST API for managing the entire plugin configuration. Users can create, edit, and delete buttons, menus, actions, and workflows through their web browser.

The typical data flow is: User clicks a button in Telegram -> `handlers.py` receives the callback -> It invokes the `ActionExecutor` to run the associated action or workflow -> The result is used to update the Telegram message, such as navigating to a new menu or displaying new information.

## Code Structure

-   `main.py`: The central hub. Contains the main `Star` plugin class, handles lifecycle events, and registers commands.
-   `handlers.py`: Processes all callback queries from Telegram buttons.
-   `actions.py`: The execution engine for all action and workflow logic.
-   `storage.py`: Defines the data models (e.g., `ButtonDefinition`, `MenuDefinition`) and manages persistence to the JSON state file.
-   `webui.py`: The `aiohttp` web server providing the management UI and REST API.
-   `config.py`: Defines the plugin's configuration schema and default values.
-   `local_actions/`: A directory containing pre-packaged, built-in "Modular Actions" that are shipped with the plugin.
-   `webui_assets/`: Contains all static assets (HTML, CSS, JavaScript) for the web interface.

## Common Commands & Development Tasks

Development and debugging of this plugin occur within the main AstrBot application.

*   **Running & Debugging**: Start the main AstrBot application. The plugin will be loaded automatically. To apply code changes, use the "Reload Plugin" functionality in the AstrBot WebUI.
*   **Formatting & Linting**: This project uses `ruff` for code quality. Run the following commands before committing changes:
    ```bash
    # Format code
    ruff format .

    # Check for linting errors
    ruff check .
    ```
*   **Managing Dependencies**: The plugin's Python dependencies are listed in `requirements.txt`. AstrBot handles their installation.
*   **Adding a Custom Action**: The recommended way to add new Python-based functionality is by creating a "Modular Action". Create a new `.py` file in the `data/plugins/astrbot_plugin_tg_button/modular_actions/` directory. The plugin will automatically detect, load, and make it available in the WebUI for use in workflows or buttons.
*   **Creating a Workflow**: Workflows are created and edited through the WebUI. You can visually chain together multiple actions (both modular and HTTP) to create complex logic.
