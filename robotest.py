"""
RoboBASIC VM:n komentorivityökalu testaamiseen.

Käyttö:
    python robotest.py <ohjelmatiedosto> [--steps N] [--debug]
    python robotest.py --interactive
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, List

from models import Robot, Position, Mine, Storage, Base, GameObject
from robobasic import RoboBASICVM, ExecutionMode


class MockMap:
    """Yksinkertainen mock-kartta testaukseen ilman map.py riippuvuutta."""
    
    def __init__(self, width: int = 20, height: int = 20):
        self.width = width
        self.height = height
        self.objects: List[GameObject] = []
    
    def add_object(self, obj: GameObject):
        """Lisää objekti karttaan."""
        self.objects.append(obj)
    
    def get_objects_in_radius(self, position: Position, radius: int) -> List[GameObject]:
        """Palauttaa objektit säteellä annetusta pisteestä."""
        result = []
        for obj in self.objects:
            distance = abs(obj.position.x - position.x) + abs(obj.position.y - position.y)
            if distance <= radius:
                result.append(obj)
        return result
    
    def in_bounds(self, position: Position) -> bool:
        """Tarkistaa onko positio kartalla."""
        return 0 <= position.x < self.width and 0 <= position.y < self.height
    
    def is_occupied(self, position: Position) -> bool:
        """Tarkistaa onko positio varattu."""
        return any(obj.position == position for obj in self.objects)
    
    def get_object_at(self, position: Position) -> Optional[GameObject]:
        """Palauttaa objektin annetussa positiossa."""
        for obj in self.objects:
            if obj.position == position:
                return obj
        return None


def luo_testikartta() -> MockMap:
    """Luo yksinkertainen testikartta roboteille."""
    kartta = MockMap(width=20, height=20)
    
    # Lisää kaivoksia
    kartta.add_object(Mine(position=Position(5, 5), material=100))
    kartta.add_object(Mine(position=Position(15, 15), material=100))
    
    # Lisää varastoja
    kartta.add_object(Storage(position=Position(10, 5), material=0))
    kartta.add_object(Storage(position=Position(10, 15), material=0))
    
    # Lisää tukikohta
    kartta.add_object(Base(position=Position(10, 10)))
    
    return kartta


def tulosta_vm_tila(robot: Robot, kartta: MockMap):
    """Tulostaa VM:n nykyisen tilan."""
    vm = robot.vm
    print("\n" + "="*60)
    print(f"ROBOTTI: {robot.name} @ {robot.position}")
    print(f"Suoritus: {vm.state.execution_mode.name}")
    print(f"PC: {vm.state.pc} / {len(vm.program.instructions) if vm.program else 0}")
    print(f"Materiaali: {robot.material}/{robot.material_capacity}")
    print(f"Kohde: {vm.state.target_position}")
    print(f"Tila: {robot.state.name}")
    
    if vm.program and 0 <= vm.state.pc < len(vm.program.instructions):
        instr = vm.program.instructions[vm.state.pc]
        print(f"Seuraava komento: {instr.command.value} {' '.join(instr.args)}")
    
    # Näytä muuttujat
    if vm.state.variables:
        print("\nMuuttujat:")
        for nimi, arvo in vm.state.variables.items():
            print(f"  {nimi} = {arvo}")
    
    # Näytä lähistön objektit
    print(f"\nLähistö (säde 3):")
    for obj in kartta.get_objects_in_radius(robot.position, 3):
        if obj != robot:
            etaisyys = abs(obj.position.x - robot.position.x) + abs(obj.position.y - robot.position.y)
            print(f"  {obj.__class__.__name__} @ {obj.position} (etäisyys: {etaisyys})")
    
    print("="*60)


def suorita_askel(robot: Robot, kartta: MockMap, debug: bool = False) -> Optional[str]:
    """Suorittaa yhden tick:n ja palauttaa mahdollisen virheen."""
    if debug:
        tulosta_vm_tila(robot, kartta)
        input("\nPaina Enter jatkaaksesi...")
    
    virhe = robot.on_tick(kartta)
    
    if virhe:
        print(f"\n[VIRHE] {virhe}")
    
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
    robot = Robot(position=Position(10, 10), name="TestBot", program="")
    
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
                robot.program = ohjelma
                robot.vm = RoboBASICVM(robot)
                robot.vm.load_program(ohjelma)
                print(f"Ladattu {len(robot.vm.program.instructions)} komentoa")
            
            elif cmd == "run":
                max_askeleet = int(komento[1]) if len(komento) > 1 else 1000
                for i in range(max_askeleet):
                    if robot.vm.state.execution_mode == ExecutionMode.STOP:
                        print(f"Ohjelma päättyi {i} askeleessa")
                        break
                    
                    virhe = suorita_askel(robot, kartta, debug=False)
                    if virhe:
                        break
                else:
                    print(f"Suoritettiin {max_askeleet} askelta")
            
            elif cmd == "step":
                suorita_askel(robot, kartta, debug=True)
            
            elif cmd == "reset":
                if robot.program:
                    robot.vm = RoboBASICVM(robot)
                    robot.vm.load_program(robot.program)
                    robot.position = Position(10, 10)
                    robot.material = 0
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
    
    # Luo testiympäristö
    kartta = luo_testikartta()
    
    # Parse position
    try:
        x, y = map(int, args.position.split(','))
        aloitus_pos = Position(x, y)
    except:
        print(f"Virheellinen positio: {args.position}")
        sys.exit(1)
    
    robot = Robot(position=aloitus_pos, name="TestBot", program=ohjelma)
    kartta.add_object(robot)
    
    print(f"Ladattu: {polku}")
    print(f"Komennot: {len(robot.vm.program.instructions)}")
    print(f"Aloituspositio: {aloitus_pos}")
    print()
    
    # Suorita ohjelma
    for askel in range(args.steps):
        if robot.vm.state.execution_mode == ExecutionMode.STOP:
            print(f"\nOhjelma päättyi onnistuneesti {askel} askeleessa")
            tulosta_vm_tila(robot, kartta)
            break
        
        virhe = suorita_askel(robot, kartta, debug=args.debug)
        
        if virhe:
            print(f"\nOhjelma keskeytetty virheeseen askeleella {askel}")
            tulosta_vm_tila(robot, kartta)
            sys.exit(1)
    else:
        print(f"\nSuoritus saavutti maksimimäärän ({args.steps} askelta)")
        tulosta_vm_tila(robot, kartta)


if __name__ == "__main__":
    main()