import webpack from 'webpack';

import { BuildOptions } from './types/config';
import { buildPlugins } from './buildPlugins';
import { buildLoaders } from './buildLoaders';
import { buildResolvers } from './buildResolvers';
import { buildDevServer } from './buildDevServer';

export function buildWebpackConfig(options: BuildOptions): webpack.Configuration {
    const { paths, mode, isDev } = options;
    return {
        mode,
        entry: paths.entry,
        output: {
            // filename: '[name].[cotenthash].js',
            filename: '[name].js',
            path: paths.build,
            clean: true,
        },
        plugins: buildPlugins(options),
        // watchOptions: {
        //     aggregateTimeout: 300,
        //     poll: 1000,
        // },
        module: {
            rules: buildLoaders(options),
        },
        resolve: buildResolvers(options),
        // devtool: 'inline-source-map',
        // devServer: buildDevServer(options),
        devtool: isDev ? 'eval-cheap-module-source-map' : undefined,
        devServer: isDev ? buildDevServer(options) : undefined,
        // externals: {
        //     jquery: 'jQuery', // Ignore jquery
        // }
    };
}
