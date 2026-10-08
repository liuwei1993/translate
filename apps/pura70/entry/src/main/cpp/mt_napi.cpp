#include "marian.h"

#include "napi/native_api.h"

#include <string>
#include <vector>

namespace {

bool read_string(napi_env env, napi_value value, std::string* out) {
    size_t length = 0;
    if (napi_get_value_string_utf8(env, value, nullptr, 0, &length) != napi_ok) {
        return false;
    }
    out->assign(length, '\0');
    size_t written = 0;
    return napi_get_value_string_utf8(env, value, out->data(), length + 1, &written) == napi_ok;
}

bool read_ids(napi_env env, napi_value value, std::vector<int64_t>* out) {
    bool is_array = false;
    if (napi_is_array(env, value, &is_array) != napi_ok || !is_array) {
        return false;
    }
    uint32_t length = 0;
    if (napi_get_array_length(env, value, &length) != napi_ok) {
        return false;
    }
    out->clear();
    out->reserve(length);
    for (uint32_t i = 0; i < length; ++i) {
        napi_value element = nullptr;
        double number = 0;
        if (napi_get_element(env, value, i, &element) != napi_ok ||
            napi_get_value_double(env, element, &number) != napi_ok) {
            return false;
        }
        out->push_back(static_cast<int64_t>(number));
    }
    return true;
}

int64_t read_int(napi_env env, napi_value value) {
    double number = 0;
    napi_get_value_double(env, value, &number);
    return static_cast<int64_t>(number);
}

void throw_message(napi_env env, const std::string& message) {
    napi_throw_error(env, nullptr, message.c_str());
}

napi_value OpenModels(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value args[2] = {nullptr, nullptr};
    napi_get_cb_info(env, info, &argc, args, nullptr, nullptr);
    if (argc < 2) {
        throw_message(env, "openModels needs encoder and decoder paths");
        return nullptr;
    }
    std::string encoder;
    std::string decoder;
    if (!read_string(env, args[0], &encoder) || !read_string(env, args[1], &decoder)) {
        throw_message(env, "model path is not a string");
        return nullptr;
    }
    std::string error;
    if (!mt_open(encoder, decoder, &error)) {
        throw_message(env, error);
    }
    return nullptr;
}

napi_value TranslateIds(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value args[3] = {nullptr, nullptr, nullptr};
    napi_get_cb_info(env, info, &argc, args, nullptr, nullptr);
    if (argc < 3) {
        throw_message(env, "translateIds needs ids, padId, eosId");
        return nullptr;
    }
    std::vector<int64_t> ids;
    if (!read_ids(env, args[0], &ids)) {
        throw_message(env, "token ids are not an array");
        return nullptr;
    }
    std::vector<int64_t> translated;
    std::string error;
    if (!mt_translate(ids, read_int(env, args[1]), read_int(env, args[2]), &translated, &error)) {
        throw_message(env, error);
        return nullptr;
    }
    napi_value result = nullptr;
    napi_create_array_with_length(env, translated.size(), &result);
    for (size_t i = 0; i < translated.size(); ++i) {
        napi_value item = nullptr;
        napi_create_double(env, static_cast<double>(translated[i]), &item);
        napi_set_element(env, result, static_cast<uint32_t>(i), item);
    }
    return result;
}

napi_value CloseModels(napi_env env, napi_callback_info info) {
    (void)info;
    mt_close();
    return nullptr;
}

napi_value Init(napi_env env, napi_value exports) {
    napi_property_descriptor desc[] = {
        {"openModels", nullptr, OpenModels, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"translateIds", nullptr, TranslateIds, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"closeModels", nullptr, CloseModels, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    napi_define_properties(env, exports, sizeof(desc) / sizeof(desc[0]), desc);
    return exports;
}

}  // namespace

static napi_module mtModule = {
    .nm_version = 1,
    .nm_flags = 0,
    .nm_filename = nullptr,
    .nm_register_func = Init,
    .nm_modname = "mt",
    .nm_priv = nullptr,
    .reserved = {0},
};

extern "C" __attribute__((constructor)) void RegisterMtModule(void) {
    napi_module_register(&mtModule);
}
