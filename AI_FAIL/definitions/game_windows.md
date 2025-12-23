# Game window descriptions
## Map
- Map of the game world
- Have scroll functionality to view different areas
- Uses colors to represent different terrains and objects
- One cell is three characters wide and one character high. Left charecter identifies object type, right characters identifies object (ID)

## Objects
- List of all buildings in the game
- One object per line
- Each line shows object type, state, and ID and other relevant info
- Have scroll functionality if too many objects to fit in window

## Events
- Log of game events
- Shows recent actions and occurrences in the game
- Newest events appear at the bottom
- Scrollable if too many events to fit in window    
- Each event entry includes a timestamp and description
    - format: W<week>D<day> HH:MM:SS <object type><object ID> <event description>

## Commands
- Command prompt for user input
- Accepts various commands to control game actions
- Displays command output and feedback
- Have history functionality to recall previous commands 
- Have scroll functionality for long outputs

# Window layout

Obejcts and Events windows are on the right side of the screen, stacked vertically. Map window is on the left side of the screen. Commands window is at the bottom of the screen, spanning the full width.

Width of Objects and Events windows is 30% of the screen width each. Height of Commands window is 20% of the screen height.

+-Map-----------+-Objects-+
|               |         |
|               |         |
|               |         |
|               |         |
+-Commands------+-Events--+
|               |         |
|               |         |
+---------------+---------+