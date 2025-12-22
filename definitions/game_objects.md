#Game objects

##General
Each game object is 2x2 cells in size on the map.
Example:
TS
ID

Definitios for cell characters:
- T: Type character
- S: Object state character
- ID: Object ID characters (two characters)

##Object types
- Robot: 'R' type character
- Rock: '#' type character
- Mine: 'M' type character
- Base: 'B' type character
- Storage: 'S' type character   

##Object states
- Idle: 'i' - object is not doing anything
- Active: 'a' - object is performing an action
- Error: 'e' - object has encountered an error
- Damaged: 'd' - object is damaged, can't do anything and needs repair

##Object IDs
- Each object has a unique two-character ID
- IDs are alphanumeric (01-99)