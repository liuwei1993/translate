#ifndef PURE70_MARIAN_H
#define PURE70_MARIAN_H

#include <cstdint>
#include <string>
#include <vector>

bool mt_open(const std::string& name, const std::string& encoder_path, const std::string& decoder_path,
    std::string* error);
void mt_close();
bool mt_translate(const std::string& name, const std::vector<int64_t>& input_ids, int64_t pad_id, int64_t eos_id,
    std::vector<int64_t>* output, std::string* error);

#endif
