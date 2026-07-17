#include "utils.h"

#include <iostream>
#include <UT/UT_Compress.h>

bool compressString(const std::string &input, std::string &output)
{
    if (input.empty())
        return false;

    UT_Compress<char> compressor;

    int stringSize = static_cast<int>(input.size());
    compressor.setChunkSize(stringSize);

    int compressedLength = 0;
    int zlibCompressionLevel = 6;

    void *compressedBufferPtr = compressor.compress(
        input.data(),
        compressedLength,
        stringSize,
        zlibCompressionLevel);

    if (!compressedBufferPtr || compressedLength <= 0)
    {
        std::cerr << "Compression failed!" << std::endl;
        return false;
    }

    output.assign(static_cast<const char *>(compressedBufferPtr), compressedLength);
    return true;
}