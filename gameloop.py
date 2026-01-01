"""Pelisilmukkamoottori KaivosAI:lle - käsittelee pelitapahtumat kiinteällä tick-taajuudella."""

import asyncio
from datetime import datetime
from typing import Optional
import database


class GameLoop:
    """Hallinnoi taustan pelitilan päivityksiä ja tapahtumien käsittelyä."""

    def __init__(self, app, dbconn, tick_rate: float = 1.0):
        """Alusta pelisilmukka.
        
        Args:
            app: Viittaus Textual-sovellusinstanssiin
            dbconn: Tietokantayhteys pelitilan tallennukseen
            tick_rate: Sekunteja pelitickien välillä (oletus 1.0 = 1 per sekunti)
        """
        self.app = app
        self.dbconn = dbconn
        self.tick_rate = tick_rate
        self.running = False
        self.paused = False
        self.tick_count = 0
        self.last_tick_time = datetime.now()

    async def run(self):
        """Pääpelisilmukka - toimii itsenäisesti taustalla."""
        self.running = True
        while self.running:
            if not self.paused:
                await self.process_tick()
            await asyncio.sleep(self.tick_rate)

    async def process_tick(self):
        """Käsittele yksi pelitick - kutsutaan joka tick_rate sekunti."""
        try:
            self.tick_count += 1
            self.last_tick_time = datetime.now()

            # Päivitä pelilogiikka
            self._update_objects()
            self._update_robots()
            self._update_mining()
            self._process_pending_commands()
            self._check_resource_transfers()

            # Kirjaa tick-tapahtuma (harvemmin roskapostin välttämiseksi)
            if self.tick_count % 10 == 0:
                database.log_event(
                    self.dbconn, "game_tick", f"Game tick {self.tick_count}"
                )

            # Ilmoita käyttöliittymälle päivityksestä
            self.app.update_game_ui()

        except Exception as e:
            database.log_event(self.dbconn, "game_error", f"Game tick error: {str(e)}")

    def _update_objects(self):
        """Kutsu jokaisen kartalla olevan objektin tikkipäivitys.

        Kutsuu `on_tick()` vain robotille, kaivokselle, varastolle ja tukikohdalle.
        """
        try:
            game_map = getattr(self.app, "game_map", None)
            if not game_map or not hasattr(game_map, "cells"):
                return
            for pos, obj in list(game_map.cells.items()):
                obj_type = type(obj).__name__.lower()
                if obj_type in {"robot", "mine", "storage", "base"}:
                    try:
                        # Kutsu objektin tikkifunktio; objektit voivat olla passiivisia
                        obj.on_tick(self.tick_count, self.tick_rate, game_map, self.dbconn)
                    except Exception:
                        # Älä kaada peliä yksittäisen objektin virheestä
                        continue
        except Exception:
            # Vältä pelin kaatuminen
            return

    def _update_robots(self):
        """Päivitä robottien sijainnit ja tilat.
        
        Huom: Robotin liikkuminen ja ohjelmasuoritus käsitellään
        Robot.on_tick():ssä, joka kutsuu vm.tick() suorittamaan RoboBASIC-käskyjä.
        """
        pass

    def _update_mining(self):
        """Päivitä kaivostoiminnot.
        
        Huom: Kaivosten materiaaliintuotanto käsitellään Mine.on_tick():ssä,
        joka nostaa material_stored-arvoa määritettävällä taajuudella.
        """
        pass

    def _process_pending_commands(self):
        """Käsittele jonossa olevat käyttäjän komennot."""
        pass

    def _check_resource_transfers(self):
        """Käsittele resurssien siirrot entiteettien välillä.
        
        Huom: Robotti LOAD/UNLOAD-siirrot käsitellään RoboBASICVM:ssä
        _process_transfers()-metodissa, joka siirtää materiaalin tick-pohjaisesti.
        """
        pass

    def pause(self):
        """Pysäytä pelisilmukka tauolle."""
        self.paused = True
        database.log_event(self.dbconn, "game_paused", "Peli pysäytetty")

    def resume(self):
        """Jatka pelisilmukkaa."""
        self.paused = False
        database.log_event(self.dbconn, "game_resumed", "Peli jatkettu")

    def stop(self):
        """Pysäytä pelisilmukka hallitusti."""
        self.running = False
        database.log_event(
            self.dbconn, "game_stop", f"Peli pysäytetty {self.tick_count} tickin jälkeen"
        )
