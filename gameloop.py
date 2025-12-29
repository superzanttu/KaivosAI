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

    def _update_robots(self):
        """Päivitä robottien sijainnit ja tilat."""
        # TODO: Toteuta robotin liikkumislogiikka
        # - Käsittele reittipisteet
        # - Päivitä sijainnit
        # - Käsittele törmäykset
        pass

    def _update_mining(self):
        """Päivitä kaivostoiminnot."""
        # TODO: Toteuta kaivoslogiikka
        # - Louhinta resursseja
        # - Päivitä kaivosten tilat
        # - Käsittele täysi varasto
        pass

    def _process_pending_commands(self):
        """Käsittele jonossa olevat käyttäjän komennot."""
        # TODO: Hae komennot jonosta ja suorita ne
        pass

    def _check_resource_transfers(self):
        """Käsittele resurssien siirrot entiteettien välillä."""
        # TODO: Toteuta siirtologiikka
        # - Robotti varastoon talletukset
        # - Tukikohta robottiin tankkaus
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
