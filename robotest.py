"""
RoboBASIC VM:n komentorivityökalu testaamiseen.

Käyttö:
    python robotest.py <ohjelmatiedosto> [--steps N] [--debug] [--trace tiedosto]
    python robotest.py --interactive
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from models import Robot, Position, Mine, Storage, Base, BaseObject
from robobasic import RoboBASICVM, ExecutionMode


class MockMap:
    """Yksinkertainen mock-kartta testaukseen ilman map.py riippuvuutta."""
    
    def __init__(self, width: int = 20, height: int = 20):
        self.width = width
        self.height = height
        self.objects: List[BaseObject] = []
        self.cells: dict = {}  # Position -> BaseObject mapping
    
    def add_object(self, obj: BaseObject):
        """Lisää objekti karttaan."""
        self.objects.append(obj)
        self.cells[obj.pos] = obj
    
    def get_objects_in_radius(self, position: Position, radius: int) -> List[BaseObject]:
        """Palauttaa objektit säteellä annetusta pisteestä."""
        result = []
        for obj in self.objects:
            distance = abs(obj.pos[0] - position[0]) + abs(obj.pos[1] - position[1])
            if distance <= radius:
                result.append(obj)
        return result
    
    def in_bounds(self, position: Position) -> bool:
        """Tarkistaa onko positio kartalla."""
        return 0 <= position[0] < self.width and 0 <= position[1] < self.height
    
    def is_occupied(self, position: Position) -> bool:
        """Tarkistaa onko positio varattu."""
        return any(obj.pos == position for obj in self.objects)
    
    def get_object_at(self, position: Position) -> Optional[BaseObject]:
        """Palauttaa objektin annetussa positiossa."""
        for obj in self.objects:
            if obj.pos == position:
                return obj
        return None


class TraceWriter:
    """Kirjoittaa trace-tiedoston ohjelman suorituksesta."""
    
    def __init__(self, filepath: str):
        """Alustaa trace-kirjoittajan.
        
        Args:
            filepath: Trace-tiedoston polku
        """
        self.filepath = filepath
        self.traces: List[str] = []
        self.step_count = 0
    
    def write_header(self, program_name: str, source_lines: List[str]):
        """Kirjoittaa trace-tiedoston otsikon."""
        self.traces.append("=" * 80)
        self.traces.append("RoboBASIC TRACE-TIEDOSTO")
        self.traces.append("=" * 80)
        self.traces.append(f"Aika: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.traces.append(f"Ohjelma: {program_name}")
        self.traces.append(f"Rivejä: {len(source_lines)}")
        self.traces.append("")
        self.traces.append("LÄHDEKOODI:")
        self.traces.append("-" * 80)
        for idx, line in enumerate(source_lines, 1):
            self.traces.append(f"{idx:03d}: {line}")
        self.traces.append("-" * 80)
        self.traces.append("")
    
    def write_step(self, robot: Robot, kartta: MockMap, source_lines: List[str], 
                   prev_instr=None, event_log: List[str] = None, error: str = None):
        """Kirjoittaa yhden suoritusaskeleen tiedot."""
        from robobasic import CommandType, Condition
        
        self.step_count += 1
        
        vm = robot.vm
        tila = vm.state
        at_target = robot.target is not None and robot.pos == robot.target
        have_target = robot.target is not None
        
        self.traces.append(f"ASKEL {self.step_count}")
        self.traces.append("-" * 80)
        
        # Suoritettu käsky
        if prev_instr:
            args_str = ' '.join(str(arg) for arg in prev_instr.args)
            
            # IF-käskyjen erityiskäsittely: näytä ehdon tosi-arvo
            if prev_instr.cmd_type == CommandType.IF:
                # args = [negated (bool), condition (Condition enum), label (str)]
                negated = prev_instr.args[0]
                condition = prev_instr.args[1]
                label = prev_instr.args[2]
                
                if isinstance(condition, Condition):
                    result = vm._evaluate_condition(condition)
                    if negated:
                        result = not result
                    condition_name = condition.name.replace('_', ' ')
                    self.traces.append(f"Suoritettu: IF {'NOT ' if negated else ''}{condition_name} GOTO {label} [{result}] (rivi {prev_instr.line_num + 1})")
                else:
                    self.traces.append(f"Suoritettu: {prev_instr.cmd_type.value} {args_str} (rivi {prev_instr.line_num + 1})")
            else:
                self.traces.append(f"Suoritettu: {prev_instr.cmd_type.value} {args_str} (rivi {prev_instr.line_num + 1})")
        
        # Robotin tila
        self.traces.append(f"Robotin tila:")
        self.traces.append(f"  Sijainti: {robot.pos}")
        self.traces.append(f"  Kohde: {robot.target}")
        self.traces.append(f"  Suoritustila: {robot.execution_mode}")
        self.traces.append(f"  Robottitila: {robot.state}")
        self.traces.append(f"  Materiaali: {robot.material_stored}/{robot.material_capacity}")
        self.traces.append(f"  AT TARGET: {at_target}, HAVE TARGET: {have_target}, BLOCKED: {robot.state == 'BLOCKED'}")
        
        # VM-tila
        self.traces.append(f"VM-tila:")
        self.traces.append(f"  PC: {tila.pc} / {len(tila.program.instructions) if tila.program else 0}")
        self.traces.append(f"  WAIT-jäljellä: {tila.wait_ticks}")
        self.traces.append(f"  LOAD-jäljellä: {tila.loading_remaining}")
        self.traces.append(f"  UNLOAD-jäljellä: {tila.unloading_remaining}")
        
        # Seuraava komento
        if tila.program and 0 <= tila.pc < len(tila.program.instructions):
            next_instr = tila.program.instructions[tila.pc]
            
            # IF-käskyjen erityiskäsittely: näytä ehdon tosi-arvo
            if next_instr.cmd_type == CommandType.IF:
                from robobasic import Condition
                negated = next_instr.args[0]
                condition = next_instr.args[1]
                label = next_instr.args[2]
                result = vm._evaluate_condition(condition)
                if negated:
                    result = not result
                condition_name = condition.name.replace('_', ' ')
                self.traces.append(f"Seuraava: IF {'NOT ' if negated else ''}{condition_name} GOTO {label} [{result}] (rivi {next_instr.line_num + 1})")
            else:
                args_str = ' '.join(str(arg) for arg in next_instr.args)
                self.traces.append(f"Seuraava: {next_instr.cmd_type.value} {args_str} (rivi {next_instr.line_num + 1})")
        
        # PRINT-viestit
        if event_log:
            self.traces.append(f"Tulostetut viestit:")
            for viesti in event_log:
                self.traces.append(f"  > {viesti}")
        
        # Virhe
        if error:
            self.traces.append(f"VIRHE: {error}")
        
        if tila.error_message:
            self.traces.append(f"VM-virhe: {tila.error_message}")
        
        self.traces.append("")
    
    def write_summary(self, robot: Robot, total_steps: int, success: bool):
        """Kirjoittaa yhteenvedon."""
        self.traces.append("=" * 80)
        self.traces.append("YHTEENVETO")
        self.traces.append("=" * 80)
        self.traces.append(f"Suoritettuja askeleita: {total_steps}")
        self.traces.append(f"Lopullinen sijainti: {robot.pos}")
        self.traces.append(f"Lopullinen kohde: {robot.target}")
        self.traces.append(f"Lopullinen materiaali: {robot.material_stored}/{robot.material_capacity}")
        self.traces.append(f"Lopullinen suoritustila: {robot.execution_mode}")
        self.traces.append(f"Onnistunut: {success}")
        self.traces.append("=" * 80)
    
    def save(self):
        """Tallentaa trace-tiedoston levylle."""
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.traces))
        print(f"\nTrace-tiedosto tallennettu: {self.filepath}")


def luo_testikartta() -> MockMap:
    """Luo yksinkertainen testikartta roboteille."""
    kartta = MockMap(width=20, height=20)
    
    # Lisää kaivoksia
    kartta.add_object(Mine(pos=(5, 5), material_stored=100))
    kartta.add_object(Mine(pos=(15, 15), material_stored=100))
    
    # Lisää varastoja
    kartta.add_object(Storage(pos=(10, 5), material_stored=0))
    kartta.add_object(Storage(pos=(10, 15), material_stored=0))
    
    # Lisää tukikohta
    kartta.add_object(Base(pos=(10, 10)))
    
    return kartta


def tulosta_vm_tila(robot: Robot, kartta: MockMap):
    """Tulostaa VM:n nykyisen tilan."""
    vm = robot.vm
    tila = vm.state
    at_target = robot.target is not None and robot.pos == robot.target
    have_target = robot.target is not None
    print("\n" + "="*60)
    print(f"ROBOTTI: {robot.name} @ {robot.pos}")
    print(f"Suoritustila: {robot.execution_mode}")
    print(f"Robottitila: {robot.state}")
    print(f"Kohde: {robot.target}")
    print(f"Sijainti: {robot.pos}")
    print(f"AT TARGET: {at_target} | HAVE TARGET: {have_target} | BLOCKED: {robot.state == 'BLOCKED'}")
    print(f"Materiaali: {robot.material_stored}/{robot.material_capacity}")
    print(f"Ohjelmalaskuri: {tila.pc} / {len(tila.program.instructions) if tila.program else 0}")
    print(f"WAIT-jäljellä: {tila.wait_ticks}")
    print(f"LOAD jäljellä: {tila.loading_remaining}")
    print(f"UNLOAD jäljellä: {tila.unloading_remaining}")
    
    if tila.program and 0 <= tila.pc < len(tila.program.instructions):
        instr = tila.program.instructions[tila.pc]
        args_str = ' '.join(str(arg) for arg in instr.args)
        print(f"Seuraava komento: {instr.cmd_type.value} {args_str}")
    
    # Näytä muuttujat (jos lisätään tulevaisuudessa)
    if hasattr(tila, 'variables') and tila.variables:
        print("\nMuuttujat:")
        for nimi, arvo in tila.variables.items():
            print(f"  {nimi} = {arvo}")
    
    # Näytä virhe jos on
    if tila.error_message:
        print(f"\nVIRHE: {tila.error_message}")
    
    # Näytä event_log viestit
    event_log = vm.get_event_log(clear=False)
    if event_log:
        print("\nTapahtumien loki (PRINT):")
        for viesti in event_log:
            print(f"  > {viesti}")
    
    # Näytä lähistön objektit
    print(f"\nLähistö (säde 3):")
    for obj in kartta.get_objects_in_radius(robot.pos, 3):
        if obj != robot:
            etaisyys = abs(obj.pos[0] - robot.pos[0]) + abs(obj.pos[1] - robot.pos[1])
            print(f"  {obj.__class__.__name__} @ {obj.pos} (etäisyys: {etaisyys})")
    
    print("="*60)


def tulosta_koodi(vm: RoboBASICVM, source_lines: List[str]):
    """Tulostaa lähdekoodin ja korostaa suoritusrivin (debug-tila)."""
    if not source_lines:
        print("(Ei ladattua ohjelmaa)")
        return

    current_instr = None
    if vm.state.program and 0 <= vm.state.pc < len(vm.state.program.instructions):
        current_instr = vm.state.program.instructions[vm.state.pc]
    current_line = current_instr.line_num if current_instr else None

    print("\nOhjelmakoodi:")
    for idx, line in enumerate(source_lines):
        lineno = idx + 1
        prefix = ">" if current_line == idx else " "
        print(f"{prefix} {lineno:03d}: {line}")

    if current_line is not None and current_line >= len(source_lines):
        print("(Suoritus viittaa koodin ulkopuoliseen riviin)")


def suorita_askel(robot: Robot, kartta: MockMap, source_lines: List[str], debug: bool = False, 
                  trace_writer: Optional[TraceWriter] = None) -> Optional[str]:
    """Suorittaa yhden tick:n ja palauttaa mahdollisen virheen."""
    # Tallenna ennen suoritusta PC ja käsky (debug-lokiin)
    # HUOM: Jos odotus aktiivinen (wait_ticks > 0), seuraava komento ei suorita, vain vähennetään
    prev_pc = robot.vm.state.pc
    prev_instr = None
    # Aseta prev_instr vain jos odotus EI ole aktiivinen (muuten seuraava komento ei suorita)
    if robot.vm.state.wait_ticks == 0 and robot.vm.state.program and 0 <= prev_pc < len(robot.vm.state.program.instructions):
        prev_instr = robot.vm.state.program.instructions[prev_pc]

    if debug:
        tulosta_koodi(robot.vm, source_lines)
        tulosta_vm_tila(robot, kartta)
        input("\nPaina Enter jatkaaksesi...")
    
    virhe = robot.on_tick(0, 0.0, kartta, None)
    
    if debug and prev_instr:
        args_str = ' '.join(str(arg) for arg in prev_instr.args)
        print(f"Suoritettu käsky: {prev_instr.cmd_type.value} {args_str} (rivi {prev_instr.line_num + 1})")
    
    # Näytä PRINT-viestit jotka tulla tällä askeleella
    event_log = robot.vm.get_event_log(clear=True)
    if event_log:
        for viesti in event_log:
            print(f"[TULOSTUS] {viesti}")
    
    if virhe:
        print(f"\n[VIRHE] {virhe}")
    
    # Kirjoita trace-tiedostoon
    if trace_writer:
        trace_writer.write_step(robot, kartta, source_lines, prev_instr, event_log, virhe)
    
    return virhe


def interaktiivinen_tila():
    """Interaktiivinen REPL-tila RoboBASIC komennoille."""
    print("RoboBASIC Interaktiivinen tila")
    print("Komennot:")
    print("  load <tiedosto>  - Lataa ohjelma tiedostosta")
    print("  run [N]          - Suorita N askelta (oletus: kaikki)")
    print("  step             - Suorita yksi askel")
    print("  reset            - Nollaa VM")
    print("  status           - Näytä tila")
    print("  quit             - Lopeta")
    print()
    
    kartta = luo_testikartta()
    robot = Robot(pos=(10, 10), name="TestBot", program_text="")
    source_lines: List[str] = []
    
    while True:
        try:
            komento = input("> ").strip().split()
            if not komento:
                continue
            
            cmd = komento[0].lower()
            
            if cmd == "quit":
                break
            
            elif cmd == "load":
                if len(komento) < 2:
                    print("Käyttö: load <tiedosto>")
                    continue
                
                polku = Path(komento[1])
                if not polku.exists():
                    print(f"Tiedostoa ei löydy: {polku}")
                    continue
                
                ohjelma = polku.read_text(encoding='utf-8')
                robot.program_text = ohjelma
                source_lines = robot.program_text.splitlines()
                robot.vm = RoboBASICVM(robot)
                robot.vm.load_program(ohjelma)
                print(f"Ladattu {len(robot.vm.state.program.instructions)} komentoa")
            
            elif cmd == "run":
                max_askeleet = int(komento[1]) if len(komento) > 1 else 1000
                for i in range(max_askeleet):
                    if robot.execution_mode == ExecutionMode.STOP.value:
                        print(f"Ohjelma päättyi {i} askeleessa")
                        break
                    
                    virhe = suorita_askel(robot, kartta, source_lines, debug=False)
                    if virhe:
                        break
                else:
                    print(f"Suoritettiin {max_askeleet} askelta")
            
            elif cmd == "step":
                suorita_askel(robot, kartta, source_lines, debug=True)
            
            elif cmd == "reset":
                if robot.program_text:
                    robot.vm = RoboBASICVM(robot)
                    robot.vm.load_program(robot.program_text)
                    source_lines = robot.program_text.splitlines()
                    robot.pos = (10, 10)
                    robot.material_stored = 0
                    print("VM nollattu")
                else:
                    print("Ei ohjelmaa ladattuna")
            
            elif cmd == "status":
                tulosta_vm_tila(robot, kartta)
            
            else:
                print(f"Tuntematon komento: {cmd}")
        
        except KeyboardInterrupt:
            print("\nKeskeytettiin")
            break
        except Exception as e:
            print(f"Virhe: {e}")


def main():
    parser = argparse.ArgumentParser(description='RoboBASIC VM testaustyökalu')
    parser.add_argument('ohjelma', nargs='?', help='RoboBASIC ohjelmatiedosto')
    parser.add_argument('--steps', '-s', type=int, default=1000, 
                       help='Maksimi askelten määrä (oletus: 1000)')
    parser.add_argument('--debug', '-d', action='store_true',
                       help='Debug-tila (askel kerrallaan)')
    parser.add_argument('--trace', '-t', type=str, default=None,
                       help='Trace-tiedoston polku suorituksen loggaamiseen')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='Interaktiivinen REPL-tila')
    parser.add_argument('--position', '-p', type=str, default='10,10',
                       help='Robotin aloituspositio (x,y)')
    
    args = parser.parse_args()
    
    if args.interactive:
        interaktiivinen_tila()
        return
    
    if not args.ohjelma:
        parser.print_help()
        return
    
    # Lataa ohjelma
    polku = Path(args.ohjelma)
    if not polku.exists():
        print(f"Virhe: Tiedostoa ei löydy: {polku}")
        sys.exit(1)
    
    ohjelma = polku.read_text(encoding='utf-8')
    source_lines = ohjelma.splitlines()
    
    # Luo testiympäristö
    kartta = luo_testikartta()
    
    # Parse position
    try:
        x, y = map(int, args.position.split(','))
        aloitus_pos = (x, y)
    except:
        print(f"Virheellinen positio: {args.position}")
        sys.exit(1)
    
    robot = Robot(pos=aloitus_pos, name="TestBot", program_text=ohjelma)
    kartta.add_object(robot)
    
    # Lataa ohjelma VM:ään
    robot.vm.load_program(ohjelma)
    
    # Käynnistä suoritus
    robot.vm.run()
    
    # Alusta trace-kirjoittaja jos pyydetty
    trace_writer = None
    if args.trace:
        trace_writer = TraceWriter(args.trace)
        trace_writer.write_header(str(polku), source_lines)
    
    print(f"Ladattu: {polku}")
    print(f"Komennot: {len(robot.vm.state.program.instructions)}")
    print(f"Aloituspositio: {aloitus_pos}")
    if args.trace:
        print(f"Trace-tiedosto: {args.trace}")
    print()
    
    # Suorita ohjelma
    success = False
    askel = 0
    for askel in range(args.steps):
        if robot.execution_mode == ExecutionMode.STOP.value:
            print(f"\nOhjelma päättyi onnistuneesti {askel} askeleessa")
            tulosta_vm_tila(robot, kartta)
            success = True
            break
        
        virhe = suorita_askel(robot, kartta, source_lines, debug=args.debug, 
                             trace_writer=trace_writer)
        
        if virhe:
            print(f"\nOhjelma keskeytetty virheeseen askeleella {askel}")
            tulosta_vm_tila(robot, kartta)
            success = False
            break
    else:
        print(f"\nSuoritus saavutti maksimimäärän ({args.steps} askelta)")
        tulosta_vm_tila(robot, kartta)
    
    # Tallenna trace-tiedosto
    if trace_writer:
        trace_writer.write_summary(robot, askel + 1, success)
        trace_writer.save()


if __name__ == "__main__":
    main()
