"""RoboBASIC 1.0 - Robot Programming Language Interpreter.

Virtuaalikone robottien ohjelmointiin KaivosAI-kaivossimulaatiossa.
BASIC-inspiroitu syntaksi yksinkertaisella label-pohjaisella hyppylogiikalla.

Miten RoboBASIC VM toimii
==========================

Arkkitehtuuri
-------------
RoboBASIC VM on per-robotti virtuaalikone, jossa jokainen robotti saa oman
VM-instanssinsa täydellä eristyksellä muista roboteista. VM:n toiminta perustuu
kolmivaiheiseen malliin: jäsennys, lataus ja suoritus.

1. **Jäsennysvaihe (Parse)**
   - RoboBASICParser lukee lähdekoodin rivi riviltä
   - Tunnistaa käskyt regex-patterneilla (16 käskytyyppiä)
   - Rakentaa Instruction-olioiden listan
   - Tallentaa labelit hyppytaulukkoon (label -> rivinumero)
   - Kerää syntaksivirheet errors-listaan
   
2. **Latasvaihe (Load)**
   - VM vastaanottaa jäsennetyn ohjelman
   - Alustaa VMState-tilan (ohjelmalaskuri, laskurit, virheet)
   - Asettaa robotin execution_mode = STOP
   - Virheellinen ohjelma -> execution_mode = ERROR

3. **Suoritusvaihe (Execute)**
   - Kutsutaan vm.run() käynnistämään suoritus
   - Joka pelitikin kohdalla kutsutaan vm.tick(game_map)
   - VM suorittaa käskyjä kunnes yksi tikki kulutettu
   - Taustaprosessit (LOAD/UNLOAD) etenevät 1 yksikkö per tikki

Suoritusmalli
-------------
**Tikin käsittely (tick-sykli):**

1. Tarkista suoritustila (RUN/STOP/ERROR)
2. Käsittele taustaprosessit (_process_transfers)
   - LOADING: Siirrä 1 materiaalia lähteestä -> robotti
   - UNLOADING: Siirrä 1 materiaalia robotti -> kohde
3. Tarkista WAIT-laskuri (jos > 0, vähennä ja lopeta)
4. Suorita käskyjä kunnes tikki kulutettu:
   - Nollatikin käskyt: GOTO, IF (hyppy), LABEL, NOP
   - Yhden tikin käskyt: MOVE, LOAD, UNLOAD, SET TARGET, WAIT, jne.
   - Lopetuskäskyt: END (-> STOP), ERROR (-> ERROR)
5. Silmukkaa ohjelman alkuun jos PC ylittää ohjelman pituuden

**Käskyjen suoritustavat:**

- **Välittömät käskyt**: Suoritetaan heti, ei tikki (GOTO, IF, LABEL, NOP)
- **Tikin käskyt**: Kuluttavat yhden tikin (MOVE, LOAD, UNLOAD, WAIT, jne.)
- **Taustakäskyt**: Aloittavat prosessin joka etenee tickeissä (LOAD, UNLOAD)

**Robotin tilakone (RobotState):**

- IDLE: Ei toimintaa, odottaa käskyjä
- MOVING: Liikkuu kohti asetettua kohdetta
- BLOCKED: Kohde asetettu mutta ei reittiä
- TARGET: Kohteessa, valmis seuraavaan käskyyn
- LOADING: Lastaa materiaalia taustalla
- UNLOADING: Purkaa materiaalia taustalla

Luokat ja tietorakenteet
=========================

Enumit (tila- ja tyypitiedot)
------------------------------

RobotState
    Robotin tila RoboBASIC-suorituksen aikana.
    Arvot: IDLE, MOVING, BLOCKED, TARGET, LOADING, UNLOADING
    Käyttö: Määrittää mitä robotti tekee ja miten se reagoi käskyihin

ExecutionMode
    Ohjelman globaali suoritustila.
    Arvot: RUN (suoritetaan), STOP (pysäytetty), ERROR (virhe)
    Käyttö: Kontrolloi onko ohjelma aktiivinen tick()-kutsuissa

CommandType
    RoboBASIC-käskytyypit jäsennyksen jälkeen.
    Arvot: NOP, LABEL, SET_TARGET_XY, SET_TARGET_ID, MOVE, UP, DOWN, LEFT, 
           RIGHT, LOAD, UNLOAD, GOTO, IF, WAIT, END, ERROR, PRINT
    Käyttö: Parser tunnistaa käskyt ja VM reitittää suorituksen tyypin mukaan

Condition
    IF-käskyn ehdolliset testit.
    Arvot: AT_TARGET, HAVE_TARGET, LOADING, UNLOADING, FULL, EMPTY
    Käyttö: Evaluoidaan runtime-aikana IF-käskyjen hyppylogiikassa

Virheluokat
-----------

RoboBASICError(GameError)
    RoboBASIC-tulkin virheet (syntaksi, suoritus, puuttuvat labelit).
    Attribuutit: message, line_num, line_text, details
    Käyttö: Nostetaan kun ohjelma ei ole validi tai suoritus epäonnistuu

Tietorakenteet
--------------

Instruction
    Yksittäinen jäsennetty RoboBASIC-käsky.
    Attribuutit:
        - cmd_type (CommandType): Käskyn tyyppi
        - args (List[Any]): Käskyn argumentit
        - line_num (int): Rivinumero lähdekoodissa (0-pohjainen)
        - raw_text (str): Alkuperäinen lähdekooodirivi
    Käyttö: Parser luo näitä jäsennyksessä, VM suorittaa niitä

ParsedProgram
    Kokonainen jäsennetty RoboBASIC-ohjelma.
    Attribuutit:
        - instructions (List[Instruction]): Käskylista järjestyksessä
        - labels (Dict[str, int]): Labelit -> rivinumerot
        - errors (List[str]): Jäsennysvirheet
    Käyttö: Parser palauttaa tämän, VM tallentaa VMState:en

VMState
    RoboBASIC VM:n sisäinen suoritustila.
    Attribuutit:
        - program (ParsedProgram): Ladattu ohjelma
        - pc (int): Ohjelmalaskuri (program counter)
        - wait_ticks (int): WAIT-käskyn jäljellä olevat tikit
        - loading_amount (Optional[int]): LOAD-käskyn määrä (None = täyteen)
        - loading_remaining (int): Lastauksen jäljellä oleva määrä
        - unloading_amount (Optional[int]): UNLOAD-käskyn määrä (None = kaikki)
        - unloading_remaining (int): Purun jäljellä oleva määrä
        - error_message (Optional[str]): Virheviesti jos suoritus epäonnistui
    Käyttö: Jokainen VM tallentaa oman tilansa, ei jaettua tilaa robottien välillä

Pääluokat
---------

RoboBASICParser
    RoboBASIC-ohjelmien jäsennin (parser).
    
    Vastuut:
        - Lukee lähdekoodin ja tunnistaa käskyt regex-patterneilla
        - Rakentaa Instruction-listan suoritusjärjestyksessä
        - Tallentaa labelit hyppytaulukkoon
        - Kerää syntaksivirheet errors-listaan
        - Validoi että kaikki GOTO/IF-labelit löytyvät
    
    Julkiset metodit:
        - parse(source_code: str) -> ParsedProgram
          Jäsentää lähdekoodin ParsedProgram-olioksi
    
    Käyttö:
        parser = RoboBASICParser()
        program = parser.parse(source_code)
        if program.errors:
            # Käsittele virheet
        else:
            # Lataa ohjelma VM:ään

RoboBASICVM
    RoboBASIC-virtuaalikone yhdelle robotille.
    
    Vastuut:
        - Suorittaa jäsennetyn ohjelman tick-pohjaisesti
        - Hallinnoi robotin tilaa (liikkuminen, lastaus, purku)
        - Käsittelee ohjausrakenteita (GOTO, IF, WAIT)
        - Siirtää materiaalit taustalla 1 yksikkö per tikki
        - Etsii reitit BFS-algoritmilla
        - Kerää tapahtumalokia (PRINT-viestit)
    
    Julkiset metodit:
        - __init__(robot): Luo VM robotille
        - load_program(source_code: str) -> List[str]: 
          Lataa ja jäsennä ohjelma, palauttaa virhelistan
        - run() -> bool: Käynnistä ohjelman suoritus
        - stop() -> None: Pysäytä suoritus
        - reset() -> None: Nollaa suoritus alkuun
        - tick(game_map) -> Optional[str]: 
          Suorita yksi pelitikki, palauttaa virheviestin jos epäonnistuu
        - get_event_log(clear: bool = False) -> List[str]: 
          Hae PRINT-viestit
        - get_state() -> VMState: Hae VM:n sisäinen tila
    
    Sisäiset metodit (execution):
        - _execute_instruction(game_map, instr): Reitittää käskyn suorituksen
        - _execute_move(game_map): Liikuttaa robottia yksi askel
        - _execute_direction(game_map, direction, amount): Suuntakäskyt
        - _execute_load(game_map, amount): Aloita lastaus
        - _execute_unload(game_map, amount): Aloita purku
        - _process_transfers(game_map): Siirrä materiaalit taustalla
        - _evaluate_condition(condition): Evaluoi IF-ehto
    
    Sisäiset metodit (apuvälineet):
        - _find_object_by_id(game_map, obj_id): Etsi objekti ID:llä
        - _find_path(game_map, start, goal): BFS-reittihaku
        - _move_robot(game_map, new_pos): Siirrä robotti uuteen sijaintiin
        - _update_robot_path_state(game_map): Päivitä tila kohteen mukaan
        - _get_adjacent_source(game_map): Etsi viereinen materiaalilähde
        - _get_adjacent_destination(game_map): Etsi viereinen materiaali kohde
    
    Käyttö:
        # Robotin __post_init__ luo VM:n automaattisesti
        robot.vm.load_program(source_code)
        errors = robot.vm.load_program(source_code)
        if not errors:
            robot.vm.run()
        
        # Joka pelitikin kohdalla
        robot.vm.tick(game_map)

Apufunktiot
-----------

create_vm(robot) -> RoboBASICVM
    Luo uuden VM-instanssin robotille.
    Käyttö: Kutsutaan Robot.__post_init__:ssä automaattisesti

Esimerkkiohjelma
================

Yksinkertainen kaivosrobotti joka louhii ja vie materiaalin tukikohtaan::

    :START
      SET TARGET #1        ; Mene kaivokselle (ID=1)
      IF NOT AT TARGET GOTO :MOVE
      
    :ATMINE
      IF FULL GOTO :GOBASE
      LOAD                 ; Lastaa kunnes täynnä
      WAIT 5               ; Odota latauksen valmistumista
      GOTO :ATMINE
      
    :GOBASE
      SET TARGET #10       ; Mene tukikohtaan (ID=10)
      IF NOT AT TARGET GOTO :MOVE
      
    :ATBASE
      IF EMPTY GOTO :START
      UNLOAD               ; Purkaa kaikki
      WAIT 5               ; Odota purun valmistumista
      GOTO :ATBASE

    :MOVE
      MOVE                 ; Liiku yksi askel kohti kohdetta
      WAIT 1               ; Odota ennen seuraavaa liikettä
      GOTO :START

    END

Suorituskulku:
    1. Asetetaan kohde kaivokselle -> RobotState.MOVING
    2. MOVE-käskyt liikuttavat robottia kunnes AT TARGET -> RobotState.TARGET
    3. LOAD aloittaa lastauksen -> RobotState.LOADING
    4. Taustalla siirtyy 1 materiaali per tikki kunnes FULL
    5. Vaihdetaan kohde tukikohtaan ja liikutaan sinne
    6. UNLOAD purkaa materiaalin -> RobotState.UNLOADING
    7. Kun EMPTY, palataan alkuun (silmukka)

Tuetut käskyt
=============

Liikkuminen:
    SET TARGET X Y      - Aseta kohde koordinaateiksi
    SET TARGET #ID      - Aseta kohde objekti-ID:llä
    MOVE                - Liiku yksi askel kohti kohdetta
    UP [N]              - Aseta kohde N ylös (oletus 1)
    DOWN [N]            - Aseta kohde N alas (oletus 1)
    LEFT [N]            - Aseta kohde N vasemmalle (oletus 1)
    RIGHT [N]           - Aseta kohde N oikealle (oletus 1)

Materiaalien käsittely:
    LOAD [N]            - Lastaa N yksikköä tai kunnes täynnä
    UNLOAD [N]          - Purkaa N yksikköä tai kaikki

Ohjausrakenteet:
    :LABEL              - Label-määritys hyppyä varten
    GOTO :LABEL         - Ehdoton hyppy labeliin
    IF cond GOTO :LABEL - Ehdollinen hyppy
    IF NOT cond GOTO :LABEL - Negaatio-ehto
    WAIT N              - Odota N tikkiä
    END                 - Lopeta ohjelma

IF-ehdot:
    AT TARGET           - Robotti on kohteessa
    HAVE TARGET         - Robotilla on kohde asetettuna
    LOADING             - Lastaus käynnissä
    UNLOADING           - Purku käynnissä
    FULL                - Varasto täynnä
    EMPTY               - Varasto tyhjä

Debugging:
    PRINT(text)         - Tulosta viesti lokiin
    ERROR(text)         - Näytä virhe ja lopeta ohjelma

Tekniset yksityiskohdat
=======================

- Parser käyttää 11 regex-patternia käskyjen tunnistamiseen
- BFS-reittihaku 4-suuntaisella liikkeellä (ei diagonaalia)
- Materiaalisiirrot 1 yksikkö per tikki realistista simulaatiota varten
- Ikusilmukkasuoja: max 1000 iteraatiota per tikki
- Labelit ovat ISOILLA KIRJAIMILLA ja NUMEROILLA (esim. :START, :LOOP1)
- Kommentit alkavat puolipisteellä (;)
- Käskyt ovat case-sensitive ja ISOILLA KIRJAIMILLA
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum
import re

from exceptions import GameError


# =============================================================================
# VAKIOT JA ENUMIT
# =============================================================================

class RobotState(Enum):
    """Robotin tila-kone RoboBASIC-suorituksen aikana.
    
    Nämä tilat hallitsevat mitä robotti tekee ja miten se reagoi käskyihin.
    Tila päivittyy automaattisesti käskyistä (SET TARGET, MOVE, LOAD, jne.)
    """
    IDLE = "IDLE"           # Ei kohdetta, ei lastaus/purkua
    MOVING = "MOVING"       # Kohde asetettu, reitti olemassa
    BLOCKED = "BLOCKED"     # Kohde asetettu, ei voi liikkua
    LOADING = "LOADING"     # Materiaalia lastataan
    UNLOADING = "UNLOADING" # Materiaalia puretaan
    TARGET = "TARGET"       # Kohteessa (goal reached)


class ExecutionMode(Enum):
    """Ohjelman globaali suoritustila.
    
    RUN: Ohjelma suoritetaan normaaleesti tick()issa
    STOP: Ohjelma ei suoritu, voidaan käynnistää run():lla
    ERROR: Ohjelmassa oli virhe, vaatii reset():ia
    """
    RUN = "RUN"     # Ohjelma suoritetaan
    STOP = "STOP"   # Ohjelma pysäytetty
    ERROR = "ERROR" # Virhetilanne


class CommandType(Enum):
    """Jäsennetyt RoboBASIC-käskyt.
    
    Jokainen käskyrivi muutetaan yhdeksi näistä tyypeistä.
    Parser tunnistaa käskyt regex-patterneja käyttämällä.
    VM suorittaa käskyt execute_instruction():ssa.
    """
    NOP = "NOP"                 # Tyhjä rivi / ei operaatiota
    LABEL = "LABEL"             # Label-määrittely
    SET_TARGET_XY = "SET TARGET XY"     # SET TARGET X Y
    SET_TARGET_ID = "SET TARGET ID"     # SET TARGET #ID
    MOVE = "MOVE"               # Liiku kohti kohdetta
    UP = "UP"                   # Suuntatyyppi ylös
    DOWN = "DOWN"               # Suuntatyyppi alas
    LEFT = "LEFT"               # Suuntatyyppi vasemmalle
    RIGHT = "RIGHT"             # Suuntatyyppi oikealle
    LOAD = "LOAD"               # Aloita lastaus
    UNLOAD = "UNLOAD"           # Aloita purku
    GOTO = "GOTO"               # Hyppää labeliin
    IF = "IF"         # Ehdollinen hyppy
    WAIT = "WAIT"               # Odota N tikkiä
    END = "END"                 # Lopeta ohjelma
    ERROR = "ERROR"     # Näytä virhe ja lopeta
    PRINT = "PRINT"             # Tulosta viesti


class Condition(Enum):
    """IF-käskyn ehdolliset testit.
    
    Nämä testit evaluoidaan runtime-aikana ja määrittelevät
    hyppäävät robotit seuraavaan labeliin vai jatkavat lineaarisesti.
    """
    AT_TARGET = "AT TARGET"
    HAVE_TARGET = "HAVE TARGET"
    LOADING = "LOADING"
    UNLOADING = "UNLOADING"
    FULL = "FULL"
    EMPTY = "EMPTY"


# =============================================================================
# VIRHELUOKAT
# =============================================================================

class RoboBASICError(GameError):
    """RoboBASIC-tulkin virhe.
    
    Nostetaan kun:
    - Syntaksivirhe ohjelmassa
    - Tuntematon käsky
    - Puuttuva label
    - Suoritusaikavirhe
    """
    
    def __init__(self, message: str, line_num: int = None, line_text: str = None):
        self.line_num = line_num
        self.line_text = line_text
        details = {}
        if line_num is not None:
            details['line_num'] = line_num
        if line_text:
            details['line_text'] = line_text
        super().__init__(message, details if details else None)


# =============================================================================
# JÄSENNYSRAKENTEET
# =============================================================================

@dataclass
class Instruction:
    """Jäsennetty RoboBASIC-käsky.
    
    Attributes:
        cmd_type: Käskyn tyyppi (CommandType)
        args: Argumenttilista (vaihtelee käskyn mukaan)
        line_num: Lähdekooodin rivinumero (0-pohjainen)
        raw_text: Alkuperäinen rivi
    """
    cmd_type: CommandType
    args: List[Any] = field(default_factory=list)
    line_num: int = 0
    raw_text: str = ""


@dataclass
class ParsedProgram:
    """Jäsennetty RoboBASIC-ohjelma.
    
    Attributes:
        instructions: Lista käskyistä suoritusjärjestyksessä
        labels: Sanakirja label -> rivinumero
        errors: Lista jäsennysvirheistä
    """
    instructions: List[Instruction] = field(default_factory=list)
    labels: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


# =============================================================================
# JÄSENNIN (PARSER)
# =============================================================================

class RoboBASICParser:
    """RoboBASIC-ohjelmien jäsennin.
    
    Jäsentää ohjelmakoodin Instruction-olioiksi ja tarkistaa labelit.
    Käskyjen jäsennys on tarkka - väärin kirjoitetut käskyt aiheuttavat virheen.
    """
    
    # Regex-patternit käskyjen tunnistamiseen
    LABEL_PATTERN = re.compile(r'^:([A-Z0-9]+)$') # :LABEL
    SET_TARGET_XY_PATTERN = re.compile(r'^SET\s+TARGET\s+(\d+)\s+(\d+)$') # SET TARGET XY int int
    SET_TARGET_ID_PATTERN = re.compile(r'^SET\s+TARGET\s+#(\d+)$') # SET TARGET ID int
    DIRECTION_PATTERN = re.compile(r'^(UP|DOWN|LEFT|RIGHT)(?:\s+(\d+))?$') # LEFT RIGHT UP DOWN | LEFT int RIGHT int UP int DOWN int
    LOAD_PATTERN = re.compile(r'^LOAD(?:\s+(\d+))?$') # LOAD | LOAD int
    UNLOAD_PATTERN = re.compile(r'^UNLOAD(?:\s+(\d+))?$') # UNLOAD | UNLOAD int
    GOTO_PATTERN = re.compile(r'^GOTO\s+:([A-Z0-9]+)$') # GOTO :LABEL
    IF_PATTERN = re.compile(
        r'^IF\s+(NOT\s+)?(AT\s+TARGET|HAVE\s+TARGET|LOADING|UNLOADING|FULL|EMPTY)\s+GOTO\s+:([A-Z0-9]+)$'
    )
    WAIT_PATTERN = re.compile(r'^WAIT\s+(\d+)$')
    ERROR_PATTERN = re.compile(r'^ERROR\s(.+)$')
    PRINT_PATTERN = re.compile(r'^PRINT\s(.+)$')
    
    def parse(self, source_code: str) -> ParsedProgram:
        """Jäsennä RoboBASIC-ohjelma.
        
        Args:
            source_code: Ohjelmakoodi merkkijonona
            
        Returns:
            ParsedProgram sisältäen käskyt ja labelit
            
        Huom:
            Jäsennysvirheet kerätään errors-listaan, ei nosteta poikkeuksia.
        """
        program = ParsedProgram()
        lines = source_code.split('\n')
        
        for line_num, line in enumerate(lines):
            instruction = self._parse_line(line, line_num)
            if instruction:
                # Label-käsittely: tallenna label-sijainti
                if instruction.cmd_type == CommandType.LABEL:
                    label_name = instruction.args[0]
                    if label_name in program.labels:
                        program.errors.append(
                            f"Rivi {line_num + 1}: Duplikaatti label '{label_name}'"
                        )
                    else:
                        program.labels[label_name] = len(program.instructions)
                
                program.instructions.append(instruction)
        
        # Tarkista että kaikki GOTO-labelit löytyvät
        self._validate_labels(program)
        
        return program
    
    def _parse_line(self, line: str, line_num: int) -> Optional[Instruction]:
        """Jäsennä yksittäinen rivi käskyksi.
        
        Args:
            line: Lähdekooodin rivi
            line_num: Rivinumero (0-pohjainen)
            
        Returns:
            Instruction tai None jos tyhjä rivi
        """
        # Poista kommentit (';' ja sen jälkeen)
        if ';' in line:
            line = line.split(';')[0]
        
        # Poista ylimääräiset välilyönnit
        line = line.strip()
        raw_text = line
        
        # Tyhjä rivi = NOP
        if not line:
            return Instruction(
                cmd_type=CommandType.NOP,
                line_num=line_num,
                raw_text=raw_text
            )
        
        # Label-tunnistus
        match = self.LABEL_PATTERN.match(line)
        if match:
            return Instruction(
                cmd_type=CommandType.LABEL,
                args=[match.group(1)],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # SET TARGET XY
        match = self.SET_TARGET_XY_PATTERN.match(line)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            return Instruction(
                cmd_type=CommandType.SET_TARGET_XY,
                args=[x, y],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # SET TARGET ID
        match = self.SET_TARGET_ID_PATTERN.match(line)
        if match:
            obj_id = int(match.group(1))
            return Instruction(
                cmd_type=CommandType.SET_TARGET_ID,
                args=[obj_id],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # MOVE
        if line == 'MOVE':
            return Instruction(
                cmd_type=CommandType.MOVE,
                line_num=line_num,
                raw_text=raw_text
            )
        
        # Suuntakäskyt: UP, DOWN, LEFT, RIGHT
        match = self.DIRECTION_PATTERN.match(line)
        if match:
            direction = match.group(1)
            amount = int(match.group(2)) if match.group(2) else 1
            cmd_type = {
                'UP': CommandType.UP,
                'DOWN': CommandType.DOWN,
                'LEFT': CommandType.LEFT,
                'RIGHT': CommandType.RIGHT
            }[direction]
            return Instruction(
                cmd_type=cmd_type,
                args=[amount],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # LOAD [N]
        match = self.LOAD_PATTERN.match(line)
        if match:
            amount = int(match.group(1)) if match.group(1) else None
            return Instruction(
                cmd_type=CommandType.LOAD,
                args=[amount],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # UNLOAD [N]
        match = self.UNLOAD_PATTERN.match(line)
        if match:
            amount = int(match.group(1)) if match.group(1) else None
            return Instruction(
                cmd_type=CommandType.UNLOAD,
                args=[amount],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # GOTO :LABEL
        match = self.GOTO_PATTERN.match(line)
        if match:
            label = match.group(1)
            return Instruction(
                cmd_type=CommandType.GOTO,
                args=[label],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # IF [NOT] condition GOTO :LABEL
        match = self.IF_PATTERN.match(line)
        if match:
            negated = match.group(1) is not None
            condition_str = match.group(2).replace('  ', ' ')  # Normalisoi välit
            label = match.group(3)
            
            # Tunnista ehto
            condition_map = {
                'AT TARGET': Condition.AT_TARGET,
                'HAVE TARGET': Condition.HAVE_TARGET,
                'LOADING': Condition.LOADING,
                'UNLOADING': Condition.UNLOADING,
                'FULL': Condition.FULL,
                'EMPTY': Condition.EMPTY
            }
            condition = condition_map.get(condition_str)
            
            return Instruction(
                cmd_type=CommandType.IF_GOTO,
                args=[negated, condition, label],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # WAIT N
        match = self.WAIT_PATTERN.match(line)
        if match:
            ticks = int(match.group(1))
            if ticks <= 0:
                return Instruction(
                    cmd_type=CommandType.ERROR_CMD,
                    args=[f"invalid wait time: {ticks}"],
                    line_num=line_num,
                    raw_text=raw_text
                )
            return Instruction(
                cmd_type=CommandType.WAIT,
                args=[ticks],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # END
        if line == 'END':
            return Instruction(
                cmd_type=CommandType.END,
                line_num=line_num,
                raw_text=raw_text
            )
        
        # ERROR TEXT 
        match = self.ERROR_PATTERN.match(line)
        if match:
            message = match.group(1)
            return Instruction(
                cmd_type=CommandType.ERROR_CMD,
                args=[message],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # PRINT TEXT
        match = self.PRINT_PATTERN.match(line)
        if match:
            message = match.group(1)
            return Instruction(
                cmd_type=CommandType.PRINT,
                args=[message],
                line_num=line_num,
                raw_text=raw_text
            )
        
        # Tuntematon käsky - palauta virhe-käsky
        return Instruction(
            cmd_type=CommandType.ERROR_CMD,
            args=[f"Tuntematon käsky: {line}"],
            line_num=line_num,
            raw_text=raw_text
        )
    
    def _validate_labels(self, program: ParsedProgram) -> None:
        """Tarkista että kaikki GOTO/IF-labelit löytyvät.
        
        Args:
            program: Jäsennetty ohjelma
        """
        for instr in program.instructions:
            if instr.cmd_type == CommandType.GOTO:
                label = instr.args[0]
                if label not in program.labels:
                    program.errors.append(
                        f"Rivi {instr.line_num + 1}: Tuntematon label '{label}'"
                    )
            elif instr.cmd_type == CommandType.IF_GOTO:
                label = instr.args[2]
                if label not in program.labels:
                    program.errors.append(
                        f"Rivi {instr.line_num + 1}: Tuntematon label '{label}'"
                    )


# =============================================================================
# VIRTUAALIKONE (VM)
# =============================================================================

@dataclass
class VMState:
    """RoboBASIC-virtuaalikoneen sisäinen tila.
    
    Attributes:
        program: Jäsennetty ohjelma
        pc: Ohjelmalaskuri (käskyindeksi)
        wait_ticks: Jäljellä olevat odotustikit
        loading_amount: Lastattava määrä (None = kunnes täynnä/tyhjä)
        loading_remaining: Jäljellä oleva lastausmäärä
        unloading_amount: Purettava määrä (None = kunnes tyhjä/täynnä)
        unloading_remaining: Jäljellä oleva purkumäärä
        error_message: Virheviesti jos suoritus päättyi virheeseen
    """
    program: ParsedProgram = None
    pc: int = 0
    wait_ticks: int = 0
    loading_amount: Optional[int] = None
    loading_remaining: int = 0
    unloading_amount: Optional[int] = None
    unloading_remaining: int = 0
    error_message: Optional[str] = None


class RoboBASICVM:
    """RoboBASIC-virtuaalikone yhdelle robotille.
    
    Jokainen robotti saa oman VM-instanssin, joka suorittaa robotin omaa
    ohjelmaa (robot.program_text) täysin itsenäisesti muista roboteista.
    
    Arkkitehtuuri:
        - Yksi VM per robotti (ei jaettua tilaa)
        - Jokainen robotti suorittaa omaa ohjelmaansa
        - Robotit eivät vaikuta toisiinsa
        - VM-tila tallennetaan robotin _vm_state-attribuuttiin
    
    Käyttö:
        # Robotti luo oman VM:n __post_init__:ssä
        robot.vm.load_program(source_code)
        robot.vm.run()
        robot.vm.tick(game_map)  # Joka pelitikin kohdalla
    """
    
    def __init__(self, robot):
        """Alusta virtuaalikone robotille.
        
        Args:
            robot: Robot-objekti jolle VM luodaan
        """
        self.robot = robot  # Viittaus omaan robottiin
        self.parser = RoboBASICParser()
        self.state: VMState = VMState()  # Robotin oma VM-tila
        # Viestiloki tapahtumille (PRINT-käskyt yms.)
        self.event_log: List[str] = []
    
    def load_program(self, source_code: str) -> List[str]:
        """Lataa ja jäsennä ohjelma.
        
        Args:
            source_code: RoboBASIC-lähdekoodi
            
        Returns:
            Lista jäsennysvirheistä (tyhjä jos onnistui)
        """
        program = self.parser.parse(source_code)
        
        # Tallenna ohjelma robotille
        self.robot.program_text = source_code
        self.robot.program_counter = 0
        
        # Alusta VM-tila
        self.state = VMState(program=program, pc=0)
        
        # Jos jäsennysvirheitä, aseta virhetilaan
        if program.errors:
            self.robot.execution_mode = ExecutionMode.ERROR.value
            self.state.error_message = "; ".join(program.errors)
            return program.errors
        
        # Pysäytä suoritus oletuksena
        self.robot.execution_mode = ExecutionMode.STOP.value
        self.robot.state = RobotState.IDLE.value
        
        return []
    
    def run(self) -> bool:
        """Käynnistä ohjelman suoritus.
        
        Returns:
            True jos käynnistys onnistui, False jos virhe
        """
        # Tarkista onko ohjelma ladattu
        if self.state.program is None:
            return False
        
        # Tarkista virheet
        if self.state.program.errors:
            self.robot.execution_mode = ExecutionMode.ERROR.value
            return False
        
        # Käynnistä
        self.robot.execution_mode = ExecutionMode.RUN.value
        self.robot.state = RobotState.IDLE.value
        
        return True
    
    def stop(self) -> None:
        """Pysäytä ohjelman suoritus."""
        self.robot.execution_mode = ExecutionMode.STOP.value
    
    def reset(self) -> None:
        """Nollaa ohjelman suoritus alkuun."""
        self.state.pc = 0
        self.state.wait_ticks = 0
        self.state.loading_amount = None
        self.state.loading_remaining = 0
        self.state.unloading_amount = None
        self.state.unloading_remaining = 0
        self.state.error_message = None
        
        self.robot.program_counter = 0
        self.robot.state = RobotState.IDLE.value
        self.robot.target = None
        self.robot.execution_mode = ExecutionMode.STOP.value
    
    def tick(self, game_map) -> Optional[str]:
        """Suorita yksi pelitikki.
        
        Args:
            game_map: Map-objekti kartta- ja objektitietoihin
            
        Returns:
            Virheviesti jos suoritus päättyi virheeseen, muuten None
        """
        robot = self.robot
        state = self.state
        
        # Tarkista onko suoritustilassa
        if robot.execution_mode != ExecutionMode.RUN.value:
            return None
        
        # Tarkista ohjelma olemassa
        if not state.program or not state.program.instructions:
            return None
        
        # Käsittele taustaprosessit ensin (LOAD/UNLOAD edistyminen)
        self._process_transfers(game_map)
        
        # Jos odotus käynnissä, vähennä laskuria
        if state.wait_ticks > 0:
            state.wait_ticks -= 1
            return None
        
        # Suorita käskyjä kunnes tikki kulutettu tai END
        tick_consumed = False
        max_iterations = 1000  # Suojaus ikuiselta silmukalta
        iterations = 0
        
        while not tick_consumed and iterations < max_iterations:
            iterations += 1
            
            # Hae nykyinen käsky
            if state.pc >= len(state.program.instructions):
                # Silmukkaa ohjelman alkuun
                state.pc = 0
            
            instr = state.program.instructions[state.pc]
            robot.program_counter = state.pc
            
            # Suorita käsky
            result = self._execute_instruction(game_map, instr)
            
            if result == 'error':
                # Virhe - pysäytä suoritus
                robot.execution_mode = ExecutionMode.ERROR.value
                return state.error_message
            
            elif result == 'end':
                # END-käsky - pysäytä suoritus
                robot.execution_mode = ExecutionMode.STOP.value
                robot.state = RobotState.IDLE.value
                return None
            
            elif result == 'tick':
                # Tikki kulutettu
                tick_consumed = True
                state.pc += 1
            
            elif result == 'jump':
                # Hyppy tehty, PC jo asetettu - ei tikki
                pass
            
            elif result == 'continue':
                # Jatka seuraavaan käskyyn (NOP, LABEL, ei-hyppäävä IF)
                state.pc += 1
        
        # Tarkista silmukkakierto
        if iterations >= max_iterations:
            state.error_message = "Ikuinen silmukka havaittu"
            robot.execution_mode = ExecutionMode.ERROR.value
            return state.error_message
        
        # Päivitä ohjelmalaskuri robotille
        robot.program_counter = state.pc
        
        return None
    
    def _execute_instruction(self, game_map, instr: Instruction) -> str:
        """Suorita yksittäinen käsky.
        
        Args:
            game_map: Map-objekti
            instr: Suoritettava käsky
            
        Returns:
            'tick' - tikki kulutettu, siirry seuraavaan
            'continue' - jatka seuraavaan (ei tikki)
            'jump' - hyppy tehty, PC jo asetettu
            'end' - END-käsky
            'error' - virhe tapahtunut
        """
        robot = self.robot
        state = self.state
        cmd = instr.cmd_type
        
        # NOP - ei tikki
        if cmd == CommandType.NOP:
            return 'continue'
        
        # LABEL - ei tikki, vain merkki
        if cmd == CommandType.LABEL:
            return 'continue'
        
        # SET TARGET XY
        if cmd == CommandType.SET_TARGET_XY:
            x, y = instr.args
            if not game_map.in_bounds((x, y)):
                state.error_message = f"invalid coordinates: {x} {y}"
                return 'error'
            robot.target = (x, y)
            self._update_robot_path_state(game_map)
            return 'tick'
        
        # SET TARGET ID
        if cmd == CommandType.SET_TARGET_ID:
            obj_id = instr.args[0]
            target_obj = self._find_object_by_id(game_map, obj_id)
            if target_obj is None:
                state.error_message = f"invalid id: {obj_id}"
                return 'error'
            robot.target = target_obj.pos
            self._update_robot_path_state(game_map)
            return 'tick'
        
        # MOVE
        if cmd == CommandType.MOVE:
            return self._execute_move(game_map)
        
        # Suuntakäskyt: UP, DOWN, LEFT, RIGHT
        if cmd in (CommandType.UP, CommandType.DOWN, 
                   CommandType.LEFT, CommandType.RIGHT):
            return self._execute_direction(game_map, cmd, instr.args[0])
        
        # LOAD
        if cmd == CommandType.LOAD:
            return self._execute_load(game_map, instr.args[0])
        
        # UNLOAD
        if cmd == CommandType.UNLOAD:
            return self._execute_unload(game_map, instr.args[0])
        
        # GOTO
        if cmd == CommandType.GOTO:
            label = instr.args[0]
            if label not in state.program.labels:
                state.error_message = f"invalid label: {label}"
                return 'error'
            state.pc = state.program.labels[label]
            return 'jump'
        
        # IF [NOT] condition GOTO
        if cmd == CommandType.IF_GOTO:
            negated, condition, label = instr.args
            result = self._evaluate_condition(condition)
            if negated:
                result = not result
            
            if result:
                if label not in state.program.labels:
                    state.error_message = f"invalid label: {label}"
                    return 'error'
                state.pc = state.program.labels[label]
                return 'jump'
            else:
                return 'continue'
        
        # WAIT
        if cmd == CommandType.WAIT:
            ticks = instr.args[0]
            state.wait_ticks = ticks
            return 'tick'
        
        # END
        if cmd == CommandType.END:
            return 'end'
        
        # ERROR TEXT
        if cmd == CommandType.ERROR_CMD:
            state.error_message = instr.args[0]
            return 'error'
        
        # PRINT TEXT
        if cmd == CommandType.PRINT:
            message = instr.args[0]
            self.event_log.append(message)
            return 'tick'
        
        # Tuntematon käsky
        state.error_message = f"Tuntematon käsky: {instr.raw_text}"
        return 'error'
    
    def _execute_move(self, game_map) -> str:
        """Suorita MOVE-käsky.
        
        Args:
            game_map: Map-objekti
            
        Returns:
            Suoritustulos ('tick', 'error', jne.)
        """
        robot = self.robot
        state = self.state
        # Tarkista onko kohdetta asetettu
        if robot.target is None:
            state.error_message = "no target set"
            return 'error'
        
        # Tarkista onko jo kohteessa
        if robot.pos == robot.target:
            robot.state = RobotState.TARGET.value
            return 'tick'
        
        # Yritä liikkua kohti kohdetta (yksi askel)
        path = self._find_path(game_map, robot.pos, robot.target)
        
        if not path or len(path) < 2:
            # Ei reittiä - blokattu
            robot.state = RobotState.BLOCKED.value
            return 'tick'
        
        # Liiku seuraavaan ruutuun polulla
        next_pos = path[1]
        
        # Tarkista voiko liikkua (ei esteitä uudessa sijainnissa)
        if game_map.is_occupied(next_pos):
            robot.state = RobotState.BLOCKED.value
            return 'tick'
        
        # Siirrä robotti
        old_pos = robot.pos
        self._move_robot(game_map, next_pos)
        
        # Päivitä tila
        if robot.pos == robot.target:
            robot.state = RobotState.TARGET.value
        else:
            robot.state = RobotState.MOVING.value
        
        return 'tick'
    
    def _execute_direction(self, game_map, direction: CommandType, amount: int) -> str:
        """Suorita suuntakäsky (UP/DOWN/LEFT/RIGHT).
        
        Laskee uuden kohteen robotin nykyisestä sijainnista.
        
        Args:
            game_map: Map-objekti
            direction: Suunta (UP/DOWN/LEFT/RIGHT)
            amount: Askelten määrä
            
        Returns:
            Suoritustulos
        """
        robot = self.robot
        state = self.state
        x, y = robot.pos
        
        # Laske uusi kohde
        if direction == CommandType.UP:
            new_y = max(0, y - amount)
            new_pos = (x, new_y)
        elif direction == CommandType.DOWN:
            new_y = min(game_map.height - 1, y + amount)
            new_pos = (x, new_y)
        elif direction == CommandType.LEFT:
            new_x = max(0, x - amount)
            new_pos = (new_x, y)
        elif direction == CommandType.RIGHT:
            new_x = min(game_map.width - 1, x + amount)
            new_pos = (new_x, y)
        else:
            state.error_message = f"invalid direction: {direction}"
            return 'error'
        
        # Aseta kohde
        robot.target = new_pos
        self._update_robot_path_state(game_map)
        
        return 'tick'
    
    def _execute_load(self, game_map, amount: Optional[int]) -> str:
        """Suorita LOAD-käsky.
        
        Aloittaa materiaalin lastauksen viereisestä lähteestä.
        
        Args:
            game_map: Map-objekti
            amount: Lastattava määrä (None = täyteen)
            
        Returns:
            Suoritustulos
        """
        robot = self.robot
        state = self.state
        
        # Etsi viereinen lähde (kaivos, varasto, tukikohta)
        adjacent = self._get_adjacent_source(game_map)
        
        if adjacent is None:
            # Ei lähdettä - epäonnistuu hiljaa
            return 'tick'
        
        # Tarkista määrä
        if amount is not None and amount <= 0:
            state.error_message = f"invalid amount: {amount}"
            return 'error'
        
        # Aloita lastaus
        state.loading_amount = amount
        if amount is not None:
            state.loading_remaining = amount
        else:
            # Lastaa kunnes täynnä tai lähde tyhjä
            free_space = robot.material_capacity - robot.material_stored
            state.loading_remaining = free_space
        
        # Peruuta mahdollinen purku
        state.unloading_amount = None
        state.unloading_remaining = 0
        
        robot.state = RobotState.LOADING.value
        
        return 'tick'
    
    def _execute_unload(self, game_map, amount: Optional[int]) -> str:
        """Suorita UNLOAD-käsky.
        
        Aloittaa materiaalin purkamisen viereiseen kohteeseen.
        
        Args:
            game_map: Map-objekti
            amount: Purettava määrä (None = kaikki)
            
        Returns:
            Suoritustulos
        """
        robot = self.robot
        state = self.state
        
        # Etsi viereinen kohde (varasto, tukikohta)
        adjacent = self._get_adjacent_destination(game_map)
        
        if adjacent is None:
            # Ei kohdetta - epäonnistuu hiljaa
            return 'tick'
        
        # Tarkista määrä
        if amount is not None and amount <= 0:
            state.error_message = f"invalid amount: {amount}"
            return 'error'
        
        # Aloita purku
        state.unloading_amount = amount
        if amount is not None:
            state.unloading_remaining = min(amount, robot.material_stored)
        else:
            # Pura kaikki
            state.unloading_remaining = robot.material_stored
        
        # Peruuta mahdollinen lastaus
        state.loading_amount = None
        state.loading_remaining = 0
        
        robot.state = RobotState.UNLOADING.value
        
        return 'tick'
    
    def _process_transfers(self, game_map) -> None:
        """Käsittele taustalla käynnissä olevat siirrot (LOAD/UNLOAD).
        
        Siirtää 1 yksikön materiaalia per tikki.
        
        Args:
            game_map: Map-objekti
        """
        robot = self.robot
        state = self.state
        
        # LOADING prosessointi
        if robot.state == RobotState.LOADING.value and state.loading_remaining > 0:
            adjacent = self._get_adjacent_source(game_map)
            if adjacent is not None:
                # Siirrä 1 yksikkö
                source_stored = getattr(adjacent, 'material_stored', 0)
                robot_space = robot.material_capacity - robot.material_stored
                
                if source_stored > 0 and robot_space > 0:
                    # Siirrä 1 yksikkö
                    adjacent.material_stored -= 1
                    robot.material_stored += 1
                    state.loading_remaining -= 1
                else:
                    # Lähde tyhjä tai robotti täynnä - lopeta
                    state.loading_remaining = 0
            else:
                # Ei lähdettä - lopeta
                state.loading_remaining = 0
            
            # Tarkista onko valmis
            if state.loading_remaining <= 0:
                state.loading_amount = None
                robot.state = RobotState.IDLE.value
        
        # UNLOADING prosessointi
        if robot.state == RobotState.UNLOADING.value and state.unloading_remaining > 0:
            adjacent = self._get_adjacent_destination(game_map)
            if adjacent is not None:
                # Siirrä 1 yksikkö
                dest_capacity = getattr(adjacent, 'material_capacity', 0)
                dest_stored = getattr(adjacent, 'material_stored', 0)
                dest_space = dest_capacity - dest_stored
                
                if robot.material_stored > 0 and dest_space > 0:
                    # Siirrä 1 yksikkö
                    robot.material_stored -= 1
                    adjacent.material_stored += 1
                    state.unloading_remaining -= 1
                else:
                    # Robotti tyhjä tai kohde täynnä - lopeta
                    state.unloading_remaining = 0
            else:
                # Ei kohdetta - lopeta
                state.unloading_remaining = 0
            
            # Tarkista onko valmis
            if state.unloading_remaining <= 0:
                state.unloading_amount = None
                robot.state = RobotState.IDLE.value
    
    def _evaluate_condition(self, condition: Condition) -> bool:
        """Evaluoi IF-käskyn ehto.
        
        Args:
            condition: Evaluoitava ehto
            
        Returns:
            True/False ehdon arvioinnin perusteella
        """
        robot = self.robot
        if condition == Condition.AT_TARGET:
            return robot.target is not None and robot.pos == robot.target
        
        if condition == Condition.HAVE_TARGET:
            return robot.target is not None
        
        if condition == Condition.LOADING:
            return robot.state == RobotState.LOADING.value
        
        if condition == Condition.UNLOADING:
            return robot.state == RobotState.UNLOADING.value
        
        if condition == Condition.FULL:
            return robot.material_stored >= robot.material_capacity
        
        if condition == Condition.EMPTY:
            return robot.material_stored == 0
        
        return False
    
    def _find_object_by_id(self, game_map, obj_id: int):
        """Etsi objekti ID:n perusteella.
        
        Args:
            game_map: Map-objekti
            obj_id: Haettava objekti-ID
            
        Returns:
            Objekti tai None jos ei löydy
        """
        for pos, obj in game_map.cells.items():
            if hasattr(obj, 'id') and obj.id == obj_id:
                return obj
        return None
    
    def _find_path(self, game_map, start: Tuple[int, int], 
                   goal: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
        """Etsi reitti BFS-algoritmilla.
        
        Args:
            game_map: Map-objekti
            start: Lähtösijainti
            goal: Kohdesijainti
            
        Returns:
            Lista sijainneista (reitti) tai None jos ei reittiä
        """
        from collections import deque
        
        if start == goal:
            return [start]
        
        # BFS reitinhaku
        queue = deque([(start, [start])])
        visited = {start}
        
        while queue:
            current, path = queue.popleft()
            
            # Naapurit (4 suuntaa)
            x, y = current
            neighbors = [
                (x + 1, y), (x - 1, y),
                (x, y + 1), (x, y - 1)
            ]
            
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                
                if not game_map.in_bounds(neighbor):
                    continue
                
                # Tarkista onko este (paitsi jos kohde)
                if neighbor != goal and game_map.is_occupied(neighbor):
                    continue
                
                visited.add(neighbor)
                new_path = path + [neighbor]
                
                if neighbor == goal:
                    return new_path
                
                queue.append((neighbor, new_path))
        
        return None  # Ei reittiä
    
    def _move_robot(self, game_map, new_pos: Tuple[int, int]) -> None:
        """Siirrä robotti uuteen sijaintiin.
        
        Args:
            game_map: Map-objekti
            new_pos: Uusi sijainti
        """
        robot = self.robot
        old_pos = robot.pos
        
        # Poista vanhasta sijainnista
        if old_pos in game_map.cells:
            del game_map.cells[old_pos]
        
        # Lisää uuteen sijaintiin
        robot.pos = new_pos
        game_map.cells[new_pos] = robot
    
    def _update_robot_path_state(self, game_map) -> None:
        """Päivitä robotin tila kohteen perusteella.
        
        Args:
            game_map: Map-objekti
        """
        robot = self.robot
        
        if robot.target is None:
            robot.state = RobotState.IDLE.value
            return
        
        if robot.pos == robot.target:
            robot.state = RobotState.TARGET.value
            return
        
        # Tarkista onko reitti olemassa
        path = self._find_path(game_map, robot.pos, robot.target)
        if path and len(path) > 1:
            robot.state = RobotState.MOVING.value
        else:
            robot.state = RobotState.BLOCKED.value
    
    def _get_adjacent_source(self, game_map):
        """Etsi viereinen materiaalilähde (kaivos, varasto, tukikohta).
        
        Args:
            game_map: Map-objekti
            
        Returns:
            Viereinen lähde tai None
        """
        from models import Mine, Storage, Base
        
        robot = self.robot
        x, y = robot.pos
        adjacent_positions = [
            (x + 1, y), (x - 1, y),
            (x, y + 1), (x, y - 1)
        ]
        
        for pos in adjacent_positions:
            if pos in game_map.cells:
                obj = game_map.cells[pos]
                # Lähteet: Mine, Storage, Base (ei robotit)
                if isinstance(obj, (Mine, Storage, Base)):
                    if getattr(obj, 'material_stored', 0) > 0:
                        return obj
        
        return None
    
    def _get_adjacent_destination(self, game_map):
        """Etsi viereinen materiaalikohde (varasto, tukikohta).
        
        Args:
            game_map: Map-objekti
            
        Returns:
            Viereinen kohde tai None
        """
        from models import Storage, Base
        
        robot = self.robot
        x, y = robot.pos
        adjacent_positions = [
            (x + 1, y), (x - 1, y),
            (x, y + 1), (x, y - 1)
        ]
        
        for pos in adjacent_positions:
            if pos in game_map.cells:
                obj = game_map.cells[pos]
                # Kohteet: Storage, Base (ei kaivokset, ei robotit)
                if isinstance(obj, (Storage, Base)):
                    capacity = getattr(obj, 'material_capacity', 0)
                    stored = getattr(obj, 'material_stored', 0)
                    if stored < capacity:
                        return obj
        
        return None
    
    def get_event_log(self, clear: bool = False) -> List[str]:
        """Hae tapahtumaloki (PRINT-viestit yms.).
        
        Args:
            clear: Tyhjennä loki haun jälkeen
            
        Returns:
            Lista viesteistä
        """
        events = list(self.event_log)
        if clear:
            self.event_log.clear()
        return events
    
    def get_state(self) -> VMState:
        """Hae VM-tila.
        
        Returns:
            VMState
        """
        return self.state


# =============================================================================
# APUFUNKTIOT
# =============================================================================

def create_vm(robot) -> RoboBASICVM:
    """Luo uusi VM-instanssi robotille.
    
    Args:
        robot: Robot-objekti jolle VM luodaan
        
    Returns:
        RoboBASICVM-instanssi
    """
    return RoboBASICVM(robot)
