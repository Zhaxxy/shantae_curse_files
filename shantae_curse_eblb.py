from typing import ClassVar, Annotated, Sequence, NamedTuple, Callable
from io import BytesIO
import struct
from dataclasses import dataclass, asdict

from PIL import Image, ImageDraw


SAVE_ENTRANCE_ID = 0x32

class ShantaeCurseEblbParsingError(Exception):
    """Error to raise if we fail to parse a eblb file, most likley a bad file given"""


class ShantaeCurseEblbBadData(ShantaeCurseEblbParsingError):
    """Error to raise if theres some bad data, eg an invalid index"""


def get_padding(strings: Sequence[str]) -> bytes:
    """Simple function to get the padding bytes from a list of strings"""
    new_bytes = b'\x00'.join(string.encode('ascii') for string in strings) + b'\x00'
    if pad_amnt := len(new_bytes) % 4:
        return b'\x00' * (4 - pad_amnt)
    return b''


class EblbObject(NamedTuple):
    underworld_type: str
    x_location: int
    y_location: int
    unknown_bool6: bool
    unknown_bool7: bool
    unknown_char8: int
    unknown_char9: int
    unknown_chara: int
    unknown_charb: int
    unknown_charb: int
    unknown_shortc: int
    unknown_inte: int

    def bbox(self,image_size: tuple = None):
        X_LENGTH = 16
        Y_LENGTH = 32
        if image_size is None:
            return (self.x_location, self.y_location + Y_LENGTH, self.x_location + X_LENGTH, self.y_location)
        return (self.x_location, image_size[1] - (self.y_location + Y_LENGTH), self.x_location + X_LENGTH, image_size[1] - self.y_location)

    @classmethod
    def from_bytes(cls, entry: Annotated[bytes, 0x14], underworld_types: list[str]):
        if len(entry) != 0x14:
            raise ShantaeCurseEblbParsingError(f'Must be 0x14 bytes an entry, not {len(entry)}')
        if entry[6] not in (0,1):
            raise ShantaeCurseEblbParsingError('Invalid boolean')
        if entry[7] not in (0,1):
            raise ShantaeCurseEblbParsingError('Invalid boolean')
        
        if entry[18] + entry[19]:
            raise ShantaeCurseEblbBadData('Invalid padding bytes, possibly wrong bytes passed into')
        
        underworld_type_index, x_location, y_location, unknown_bool6, unknown_bool7, unknown_char8, unknown_char9, unknown_chara, unknown_charb, unknown_shortc, unknown_inte,_,_ = struct.unpack('<H2h2?4BhIBB',entry)
        underworld_type = underworld_types[underworld_type_index - 1]
        return cls(underworld_type = underworld_type, 
                    x_location = x_location, 
                    y_location = y_location,
                    unknown_bool6 = unknown_bool6,
                    unknown_bool7 = unknown_bool7,
                    unknown_char8 = unknown_char8,
                    unknown_char9 = unknown_char9,
                    unknown_chara = unknown_chara,
                    unknown_charb = unknown_charb,
                    unknown_shortc = unknown_shortc,
                    unknown_inte = unknown_inte
                    )

    def to_bytes(self, underworld_types: list[str]) -> bytes:
        underworld_type_index = underworld_types.index(self.underworld_type) + 1
        return struct.pack('<H2h2?4BhIBB',underworld_type_index,
                        self.x_location,
                        self.y_location,
                        self.unknown_bool6,
                        self.unknown_bool7,
                        self.unknown_char8,
                        self.unknown_char9,
                        self.unknown_chara,
                        self.unknown_charb,
                        self.unknown_shortc,
                        self.unknown_inte,
                        0,0)


class EntranceAndOrExit(NamedTuple):
    x1: int
    y1: int
    x2: int
    y2: int
    entrance_id: int
    exit_type_id: int
    exit_location_id: int
    entrance_type_id: int
    exit_scene_name: str

    def bbox(self,image_size: tuple = None):
        if image_size is None:
            return ((self.x1,self.y2),(self.x2,self.y2))
        return ((self.x1,image_size[1] - self.y1),(self.x2,image_size[1] - self.y2))
        
    @classmethod
    def from_bytes(cls,entry: Annotated[bytes, 0x1c], exit_name: str = ''):
        x1,y1,x2,y2,entrance_id,exit_type_id,exit_location_id,entrance_type_id = struct.unpack('<5iHIH',entry)
        return cls(
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            entrance_id=entrance_id,
            exit_type_id=exit_type_id,
            exit_location_id=exit_location_id,
            entrance_type_id=entrance_type_id,
            exit_scene_name=exit_name
        )

    def to_bytes(self):
        return struct.pack('<5iHIH',
                           self.x1,
                           self.y1,
                           self.x2,
                           self.y2,
                           self.entrance_id,
                           self.exit_type_id,
                           self.exit_location_id,
                           self.entrance_type_id) + self.exit_scene_name.encode('ascii') + b'\x00' + get_padding((self.exit_scene_name,))


@dataclass(slots=True)
class ShantaeCurseEblb:
    UNDERWORLD_TYPES_TYP: ClassVar[bytes] = b'UNDERWORLD_TYPES_TYP\x00'

    objects: list[EblbObject]
    doors: list[EntranceAndOrExit]
    camera_x1: int
    camera_y1: int
    camera_x2: int
    camera_y2: int
    tiles: list[list[int]]
    
    @classmethod
    def from_eblb_file(cls, eblb_file: BytesIO):
        eblb_file.seek(0)
        objects_count, unknown_short, doors_count, underworld_types_count, tiles_x, tiles_y = struct.unpack('<4H2I',eblb_file.read(0x10))
        self_objects = []
        self_doors = []

        if unknown_short != 1:
            raise ShantaeCurseEblbParsingError(f'it should be 1, not {unknown_short}')

        if not eblb_file.read(len(cls.UNDERWORLD_TYPES_TYP)) == cls.UNDERWORLD_TYPES_TYP:
            raise ShantaeCurseEblbParsingError('There was no UNDERWORLD_TYPES_TYP string')

        underworld_types = []
        for _ in range(underworld_types_count):
            new_string = b''.join(iter(lambda: eblb_file.read(1),b'\x00'))
            underworld_types.append(new_string.decode('ascii'))

        eblb_file.seek(len(get_padding([cls.UNDERWORLD_TYPES_TYP.removesuffix(b'\x00').decode('ascii')] + underworld_types)),1)

        for _ in range(objects_count):
            self_objects.append(EblbObject.from_bytes(eblb_file.read(0x14),underworld_types))

        self_camera_x1, self_camera_y1, self_camera_x2, self_camera_y2, unknown_int_should_be_0 = struct.unpack('<5i',eblb_file.read(0x14))

        if unknown_int_should_be_0:
            raise ShantaeCurseEblbParsingError(f'it should be 0, not {unknown_int_should_be_0}!')

        for _ in range(doors_count):
            door_bytes = eblb_file.read(0x1c)
            exit_scene_name = b''.join(iter(lambda: eblb_file.read(1),b'\x00')).decode('ascii')
            eblb_file.seek(len(get_padding((exit_scene_name,))),1)
            self_doors.append(EntranceAndOrExit.from_bytes(door_bytes,exit_scene_name))
        
        self_tiles = eblb_file.read()
        if not len(self_tiles) == tiles_x * tiles_y:
            raise ShantaeCurseEblbBadData('The tiles does not match the dimension')
        self_tiles = [list(self_tiles[i:i+tiles_x]) for i in range(0, len(self_tiles), tiles_x)]
        
        eblb_file.seek(0)
        return cls(objects = self_objects, 
                    doors = self_doors, 
                    camera_x1 = self_camera_x1, 
                    camera_y1 = self_camera_y1, 
                    camera_x2 = self_camera_x2,
                    camera_y2 = self_camera_y2, 
                    tiles = self_tiles)

    def camera_bbox(self,image_size: tuple = None):
        if image_size is None:
            return ((self.camera_x1,self.camera_y1),(self.camera_x2,self.camera_y2))
        return ((self.camera_x1,image_size[1] - self.camera_y1),(self.camera_x2,image_size[1] - self.camera_y2))

    def check_eblb(self):
        for row in self.tiles:
            if not len(row) == len(self.tiles[0]):
                raise ShantaeCurseEblbBadData('Invalid 2d tiles')
    
    @classmethod
    def from_dict(cls,json_dict: dict):
        json_dict['objects'] = [EblbObject(**x) for x in json_dict['objects']]
        json_dict['doors'] = [EntranceAndOrExit(**x) for x in json_dict['doors']]
        return cls(**json_dict)
        
    def to_dict(self):
        json_dict = asdict(self)
        json_dict['objects'] = [x._asdict() for x in self.objects]
        json_dict['doors'] = [x._asdict() for x in self.doors]
        return json_dict
        
    def __bytes__(self) -> bytes:
        self.check_eblb()
        eblb_file = BytesIO()
        underworld_types = list({entry.underworld_type for entry in self.objects})
        
        eblb_file.write(struct.pack('<4H2I',len(self.objects), 1, len(self.doors), len(underworld_types), len(self.tiles[0]), len(self.tiles)))
        eblb_file.write(
                    self.UNDERWORLD_TYPES_TYP +
                    b'\x00'.join(string.encode('ascii') for string in underworld_types) + 
                    b'\x00' + 
                    get_padding([self.UNDERWORLD_TYPES_TYP.removesuffix(b'\x00').decode('ascii')] + underworld_types)
                    )


        for entry in self.objects:
            eblb_file.write(entry.to_bytes(underworld_types))

        eblb_file.write(struct.pack('<5i',self.camera_x1, self.camera_y1, self.camera_x2, self.camera_y2, 0))
        
        for door in self.doors:
            eblb_file.write(door.to_bytes())
        eblb_file.write(bytes([j for sub in self.tiles for j in sub]))
        return eblb_file.getvalue()
    
    def image_layout(self, /, *,
                    draw_tiles: bool = True,
                    draw_camera_border: bool = True,
                    draw_doors: bool | list[EntranceAndOrExit] = True,
                    draw_objects: bool | list[EblbObject] = True,
                    tiles_colour_dict: dict[int, tuple[int, int, int]] = None,
                    draw_doors_function: None | Callable[[Image, EntranceAndOrExit], Image] = None,
                    draw_object_function: None | Callable[[Image, EblbObject], Image] = None,
                    ) -> Image:
        """A nice layout to see the level, this also has the correct dimesions to be the background image for the level"""
        self.check_eblb()
        layout_look = Image.new("RGB", (len(self.tiles[0]), len(self.tiles)))

        default_colours =  {
                0:  (0, 0, 0),      # Black
                1:  (230, 230, 250),# lavender
                3:  (128, 0, 128),  # Purple
                7:  (0, 128, 128),
                9:  (255, 165, 0),  # Orange
                11: (70, 0, 0),     # Dark Brown
                12: (0, 0, 255),    # Blue
                13: (255, 255, 0),  # Yellow
                14: (175, 238, 238),# Pale Cyan
                15: (255, 0, 255),  # Magenta
                16: (0, 255, 255),  # Cyan
                22: (255, 192, 203),# Pink
                24: (128, 0, 0),    # Maroon
                25: (128, 128, 0),  #
                27: (128, 128, 128),# Grey
                28: (150, 75, 0),   # Brown
                31: (1, 50, 32),    # Dark Green
            }

        if tiles_colour_dict is None:
            tiles_colour_dict = default_colours

        layout_look.putdata([tiles_colour_dict[tile] for tile in [j for sub in self.tiles for j in sub]]) if draw_tiles else None
        layout_look = layout_look.resize((layout_look.size[0]*16,layout_look.size[1]*16),Image.NEAREST)
        draw = ImageDraw.Draw(layout_look)
        
        if draw_doors:
            if draw_doors is True:
                draw_doors = self.doors
            for door in draw_doors:
                if draw_doors_function is None:
                    draw.rectangle(door.bbox(layout_look.size),outline=(0, 255, 0))
                else:
                    layout_look = draw_doors_function(layout_look, door)

        if draw_objects:
            if draw_objects is True:
                draw_objects = self.objects
            for eblb_object in draw_objects:
                if draw_object_function is None:
                    draw.rectangle(eblb_object.bbox(layout_look.size),outline=(255, 0, 0), width=3)
                else:
                    layout_look = draw_object_function(layout_look, eblb_object)
        
        if draw_camera_border:
            draw.rectangle(self.camera_bbox(layout_look.size),outline=(255,255,255))
        return layout_look


def main():
    with open('IB_04.eblb','rb') as f:
        sc = ShantaeCurseEblb.from_eblb_file(f)
    
    sc.image_layout().save('wat.png')

    import json
    
    with open('ass.json','w') as f:
        json.dump(sc.to_dict(),f, indent=4)

if __name__ == '__main__':
    main()