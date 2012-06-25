"""
Brute-force bitwise analysis of transformations and analysers.

Created on Feb 15, 2012
"""

__author__ = 'Peter May (Peter.May@bl.uk), Andrew Jackson (Andrew.Jackson@bl.uk)'
__license__ = 'Apache Software License, Version 2.0'
__version__ = '0.0.2'

from io import FileIO
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import hashlib
from string import Template

#CMD_CONVERT = "C:/Program Files/ImageMagick-6.7.3-Q16/convert"
CMD_CONVERT = "convert"

TMPL_CONVERT = Template("convert ${in_file} ${out_file.jp2}")
#===============================================================================
# s.substitute(who='tim', what='kung pao')
#
# identify -verbose src/test/resources/chrome_32x32_lzw.tif > identify.out
# jpylyzer
# jp2structCheck
# file
# TIKA? VSLOW
# DROID? VVSLOW
#===============================================================================

class Output:
    def __init__(self, exitcode, stdout, stderr):
        self.exitcode = exitcode
        self.stdout   = stdout
        self.stderr   = stderr
        
class BitManipulator(object):
    
    @staticmethod
    def flipAt(inputfile, position, byteflipping=False):
        if byteflipping:
            BitManipulator.flipByteAt(inputfile, position)
        else:
            BitManipulator.flipBitAt(inputfile, position)
            
    
    @staticmethod
    def flipByteAt(inputfile, position):
        """Flips the bits for the byte at the specified position in the input file."""
        f = FileIO(inputfile, "r+")
        f.seek(position)
        byte = ord(f.read(1))
        f.seek(-1, 1)   # go back 1 byte from current position
        f.write(struct.pack("B", byte^0xFF))    # read in the byte and XOR it
        f.close()
        
    @staticmethod
    def flipBitAt(inputfile, position):
        """Flips the bit at the specified position in the input file."""
        if not 0<=position<(8*os.path.getsize(inputfile)):
            raise IndexError("Position "+str(position)+" is out of range")
        
        f = FileIO(inputfile, "r+")
        f.seek(position/8)
        byte = ord(f.read(1))
        f.seek(-1, 1)   # go back 1 byte from the current position
        bitnum = position%8
        f.write(struct.pack("B", byte^(1<<(7-bitnum))))
        f.close()
        
    @staticmethod
    def bits(file):
        """Exposes bits from the specified file as a Generator"""
        bytes = (ord(b) for b in file.read())
        for b in bytes:
            for i in xrange(8):
                yield (b>>i)&1
                
    @staticmethod
    def getBitFromByteAt(byte, position):
        """Returns the bit at the specified position"""
        if not 0<=position<8:
            raise IndexError("Position "+str(position)+" is out of range")
        return (byte>>(7-position))&1
    

def md5sum(filename):
    md5 = hashlib.md5()
    with open(filename,'rb') as f: 
        for chunk in iter(lambda: f.read(128*md5.block_size), b''): 
             md5.update(chunk)
    return md5.hexdigest()

def analyse(testfile, byteflipping=False):
    """Run the convert command on the specified input test file.
    
       If True, byteflipping indicates that whole bytes should be flipped,
       rather than the default individual bits.
       
    """
    # Store the absolute path of the test file
    testfile = os.path.abspath(testfile)
    
    # create a temporary folder to run in, and cd into it:
    tmp_dir = tempfile.mkdtemp()
    saved_path = os.getcwd()
    os.chdir(tmp_dir)
    
    # create a temporary file for bit manipulation
    tmp_file = os.path.basename(testfile)
    shutil.copyfile(testfile, tmp_file)
    
    # run command on original to get desired output for comparison
    out_file = "out.jp2"
    expected = __runCommand(CMD_CONVERT, tmp_file, out_file)
    expected_md5 = md5sum(out_file)

    # stats
    clear = 0
    error = 0
    out_unchanged = 0
    out_changed = 0
    out_none = 0
    
    # open temporary file and flip bits/bytes
    filelen = os.path.getsize(tmp_file) if byteflipping else 8*os.path.getsize(tmp_file)
    for i in xrange(filelen):
        # Flip bit/byte
        BitManipulator.flipAt(tmp_file, i, byteflipping)
        # Run the program again:
        output = __runCommand(CMD_CONVERT, tmp_file, out_file)
        # Flip the bit(s) back
        BitManipulator.flipAt(tmp_file, i, byteflipping)
        
        # Check and clean up:
        if output.exitcode==expected.exitcode:
            clear+=1
        else:
            error+=1
        # Is there a file, and is it the same as before?
        if os.path.exists(out_file):
            md5 = md5sum(out_file)
            if md5 == expected_md5:
                out_unchanged+=1
            else:
                out_changed+=1
            os.remove(out_file)
        else:
            out_none+=1

        # Report percentage complete:        
        if not i%100:
            print "Completed (%d/%d): %d%%"%(i+1,filelen,(100*(i+1)/filelen))

    # clear up
    if os.path.exists(tmp_file):
        os.remove(tmp_file)
    shutil.rmtree(tmp_dir)
    
    # chdir back:
    os.chdir(saved_path)
    
    # and return
    return (clear, error, out_none, out_unchanged, out_changed)

def __runCommand(command, inputfile, outputfile):
    """Runs the specified command on the specified input file.
    
       returns: Output object
       
    """
    #print sys.platform
    # See http://www.activestate.com/blog/2007/11/supressing-windows-error-report-messagebox-subprocess-and-ctypes
    # and http://stackoverflow.com/questions/5069224/handling-subprocess-crash-in-windows
    subprocess_flags = 0
    if sys.platform.startswith("win"):
        import ctypes
        SEM_NOGPFAULTERRORBOX = 0x0002  # From http://msdn.microsoft.com/en-us/library/ms680621(VS100).aspx
        ctypes.windll.kernel32.SetErrorMode(SEM_NOGPFAULTERRORBOX) #@UndefinedVariable
        subprocess_flags = 0x8000000    # win32con.CREATE_NO_WINDOW

    process = subprocess.Popen([command, inputfile, outputfile], 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                               creationflags=subprocess_flags)

    exitcode = process.wait()
    output = process.communicate()
    
    return Output(exitcode, output[0], output[1])



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Bitwise Analyser over the specified command')
    parser.add_argument('file', help='example input file to test with')
    parser.add_argument('--bytes', action='store_true', help='use byte-level flipping, rather than bit flipping')
    
    args = parser.parse_args()
    results = analyse(args.file, args.bytes)
    print "Results compared to original file execution:"
    print " #Byte mods causing expected exit code:  ",results[0]
    print " #Byte mods causing unexpected exit code:",results[1]
    print " #Byte mods causing no output:           ",results[2]
    print " #Byte mods causing identical output:    ",results[3]
    print " #Byte mods causing changed output:      ",results[4]
    